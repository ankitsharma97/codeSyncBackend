import json

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

        self.assertTrue(await RoomDocument.objects.filter(room='r2').aexists())
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
