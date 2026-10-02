import json
import zlib

from channels.testing import WebsocketCommunicator
from django.test import TransactionTestCase
from pycrdt import Doc, Text, YMessageType, create_sync_message, create_update_message, handle_sync_message

from codeSync.asgi import application
from main import awareness, rooms
from main.models import RoomDocument


class Client:
    """A y-websocket-like client: owns a Doc and answers sync messages."""

    def __init__(self, room):
        self.doc = Doc()
        self.text = self.doc.get('codemirror', type=Text)
        self.ws = WebsocketCommunicator(application, f'/ws/code_sync/{room}')
        self.awareness = []

    async def connect(self):
        connected, _ = await self.ws.connect()
        assert connected
        await self.ws.send_to(bytes_data=create_sync_message(self.doc))
        await self.pump()

    async def pump(self):
        """Process everything the server has queued for us."""
        while not await self.ws.receive_nothing(timeout=0.2):
            data = await self.ws.receive_from()
            if data[0] == YMessageType.SYNC:
                reply = handle_sync_message(data[1:], self.doc)
                if reply is not None:
                    await self.ws.send_to(bytes_data=reply)
            else:
                self.awareness.append(awareness.parse(data))

    async def type(self, value):
        before = self.doc.get_state()
        self.text += value
        await self.ws.send_to(bytes_data=create_update_message(self.doc.get_update(before)))

    async def disconnect(self):
        await self.ws.disconnect()


class CollabTests(TransactionTestCase):
    async def test_edits_reach_other_clients(self):
        a, b = Client('r1'), Client('r1')
        await a.connect()
        await b.connect()
        await a.type('hello')
        await b.pump()
        self.assertEqual(str(b.text), 'hello')
        await b.type(' world')
        await a.pump()
        self.assertEqual(str(a.text), 'hello world')
        await a.disconnect()
        await b.disconnect()

    async def test_late_joiner_gets_state_and_it_persists(self):
        a = Client('r2')
        await a.connect()
        await a.type('def f(): pass')
        await a.pump()
        await a.disconnect()  # last one out: state is flushed to the DB

        row = await RoomDocument.objects.aget(room='r2')
        self.assertTrue(row.compressed)
        zlib.decompress(bytes(row.state))  # stored deflated
        self.assertNotIn('r2', rooms._rooms)

        b = Client('r2')
        await b.connect()
        self.assertEqual(str(b.text), 'def f(): pass')
        await b.disconnect()

    async def test_rooms_are_isolated(self):
        a, b = Client('r3'), Client('r4')
        await a.connect()
        await b.connect()
        await a.type('secret')
        await b.pump()
        self.assertEqual(str(b.text), '')
        await a.disconnect()
        await b.disconnect()

    async def test_awareness_replayed_to_newcomer_and_removed_on_disconnect(self):
        a = Client('r5')
        await a.connect()
        state = json.dumps({'user': {'name': 'ann'}})
        await a.ws.send_to(bytes_data=awareness.encode([(42, 1, state)]))

        b = Client('r5')
        await b.connect()
        self.assertEqual(b.awareness, [[(42, 1, state)]])

        await a.disconnect()
        await b.pump()
        self.assertEqual(b.awareness[-1], [(42, 2, 'null')])
        await b.disconnect()

    async def test_malformed_message_closes_socket(self):
        a = Client('r6')
        await a.connect()
        await a.ws.send_to(bytes_data=bytes([0, 2, 3, 255, 255, 255]))
        out = await a.ws.receive_output(timeout=1)
        self.assertEqual(out['type'], 'websocket.close')

    async def test_rows_saved_before_compression_still_load(self):
        doc = Doc()
        text = doc.get('codemirror', type=Text)
        text += 'legacy code'
        await RoomDocument.objects.acreate(room='old', state=doc.get_update(), compressed=False)

        b = Client('old')
        await b.connect()
        self.assertEqual(str(b.text), 'legacy code')
        await b.disconnect()


class GitProxyTests(TransactionTestCase):
    """The proxy must only ever reach git endpoints on allow-listed hosts."""

    def get(self, target, **extra):
        from django.test import Client as HttpClient
        return HttpClient().get(f'/git-proxy/{target}', **extra)

    def test_rejects_hosts_and_paths_outside_the_allowlist(self):
        for target in [
            'evil.com/o/r.git/info/refs?service=git-upload-pack',
            'localhost/o/r.git/info/refs',
            '169.254.169.254/latest/meta-data/info/refs',
            'github.com@evil.com/o/r.git/info/refs',
            'github.com:8080/o/r.git/info/refs',
            'github.com/o/r.git/../../etc/passwd',
            'github.com/o/r.git/settings/secrets',
            'github.com/o/r.git',
        ]:
            self.assertEqual(self.get(target).status_code, 403, target)

    def test_method_and_service_rules(self):
        from django.test import Client as HttpClient
        self.assertEqual(self.get('github.com/o/r.git/info/refs').status_code, 400)  # no service
        self.assertEqual(HttpClient().post('/git-proxy/github.com/o/r.git/info/refs?service=git-upload-pack').status_code, 405)
        self.assertEqual(HttpClient().get('/git-proxy/github.com/o/r.git/git-upload-pack').status_code, 405)

    def test_preflight_has_cors_headers(self):
        from django.test import Client as HttpClient
        response = HttpClient().options('/git-proxy/github.com/o/r.git/info/refs', HTTP_ORIGIN='http://localhost:3000')
        self.assertEqual(response.status_code, 204)
        self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:3000')
        self.assertIn('Authorization', response['Access-Control-Allow-Headers'])

    def test_forwards_to_upstream_and_passes_auth_through(self):
        import io
        from unittest import mock
        from main import gitproxy

        seen = {}

        class FakeResponse(io.BytesIO):
            status = 200
            headers = {'Content-Type': 'application/x-git-upload-pack-advertisement'}

        def fake_open(req, timeout=None):
            seen['url'], seen['auth'], seen['method'] = req.full_url, req.get_header('Authorization'), req.get_method()
            return FakeResponse(b'001e# service=git-upload-pack\n0000')

        with mock.patch.object(gitproxy._opener, 'open', side_effect=fake_open):
            response = self.get('github.com/octocat/Hello-World.git/info/refs?service=git-upload-pack', HTTP_AUTHORIZATION='Basic abc')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen['url'], 'https://github.com/octocat/Hello-World.git/info/refs?service=git-upload-pack')
        self.assertEqual(seen['auth'], 'Basic abc')
        self.assertEqual(response['Content-Type'], 'application/x-git-upload-pack-advertisement')
        self.assertIn(b'git-upload-pack', response.content)

    def test_post_is_forwarded_with_body_and_oversized_bodies_are_refused(self):
        import io
        from unittest import mock
        from django.test import Client as HttpClient
        from main import gitproxy

        seen = {}

        class FakeResponse(io.BytesIO):
            status = 200
            headers = {'Content-Type': 'application/x-git-upload-pack-result'}

        def fake_open(req, timeout=None):
            seen['method'], seen['body'], seen['type'] = req.get_method(), req.data, req.get_header('Content-type')
            return FakeResponse(b'0008NAK\n')

        url = '/git-proxy/github.com/octocat/Hello-World.git/git-upload-pack'
        with mock.patch.object(gitproxy._opener, 'open', side_effect=fake_open):
            ok = HttpClient().post(url, data=b'0032want abc\n', content_type='application/x-git-upload-pack-request',
                                   HTTP_ORIGIN='http://localhost:3000')
            too_big = HttpClient().post(url, data=b'x', content_type='application/x-git-upload-pack-request',
                                        CONTENT_LENGTH=str(gitproxy.MAX_REQUEST_BYTES + 1))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual((seen['method'], seen['body']), ('POST', b'0032want abc\n'))
        self.assertEqual(seen['type'], 'application/x-git-upload-pack-request')
        self.assertEqual(ok['Access-Control-Allow-Origin'], 'http://localhost:3000')
        self.assertEqual(too_big.status_code, 413)

    def test_unexpected_errors_still_carry_cors_headers(self):
        from unittest import mock
        from django.test import Client as HttpClient
        from main import gitproxy

        with mock.patch.object(gitproxy._opener, 'open', side_effect=RuntimeError('boom')):
            response = HttpClient().get('/git-proxy/github.com/o/r.git/info/refs?service=git-upload-pack', HTTP_ORIGIN='http://localhost:3000')
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response['Access-Control-Allow-Origin'], 'http://localhost:3000')
