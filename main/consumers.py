import asyncio
import logging

from channels.generic.websocket import AsyncWebsocketConsumer
from pycrdt import YMessageType, YSyncMessageType, create_sync_message, handle_sync_message

from . import awareness, rooms

logger = logging.getLogger(__name__)

MAX_MESSAGE_BYTES = 2 * 1024 * 1024
_UPDATES = (YSyncMessageType.SYNC_STEP2, YSyncMessageType.SYNC_UPDATE)


class CodeSyncConsumer(AsyncWebsocketConsumer):
    """Speaks the y-websocket protocol (sync + awareness) for one room.

    The server keeps a Yjs doc per room so late joiners get the full document
    even when nobody else is online, and persists it to the DB.
    """

    async def connect(self):
        name = self.scope['url_route']['kwargs']['room']
        self.group_name = f'room.{name}'
        self.room = await rooms.join(name, self.channel_name)
        await self.channel_layer.group_add(self.group_name, self.channel_name)
        await self.accept()

        # Ask the client for whatever it has that the server lacks, and show it who is here.
        await self.send(bytes_data=create_sync_message(self.room.doc))
        snapshot = self.room.awareness_snapshot()
        if snapshot:
            await self.send(bytes_data=snapshot)

    async def disconnect(self, code):
        if not hasattr(self, 'room'):
            return
        await self.channel_layer.group_discard(self.group_name, self.channel_name)
        for message in self.room.drop_channel(self.channel_name):
            await self._relay(message)
        await rooms.leave(self.room, self.channel_name)

    async def receive(self, text_data=None, bytes_data=None):
        if not bytes_data or len(bytes_data) > MAX_MESSAGE_BYTES:
            await self.close(code=1009)
            return
        try:
            if bytes_data[0] == YMessageType.SYNC:
                reply = handle_sync_message(bytes_data[1:], self.room.doc)
                if reply is not None:
                    await self.send(bytes_data=reply)
                if bytes_data[1] in _UPDATES:
                    self.room.mark_dirty()
                    await self._relay(bytes_data)
            elif bytes_data[0] == YMessageType.AWARENESS:
                self.room.track_awareness(self.channel_name, bytes_data)
                await self._relay(bytes_data)
        except asyncio.CancelledError:
            raise
        except BaseException:  # pycrdt < 0.14 reports corrupt updates as a Rust panic (BaseException)
            logger.warning('Malformed message in %s', self.group_name, exc_info=True)
            await self.close(code=1003)

    async def _relay(self, data):
        await self.channel_layer.group_send(
            self.group_name, {'type': 'relay', 'sender': self.channel_name, 'data': data}
        )

    async def relay(self, event):
        sender, data = event['sender'], event['data']
        if sender == self.channel_name:
            return
        if sender not in self.room.channels:
            # Came from another server process: mirror it into this process's copy.
            if data[0] == YMessageType.SYNC:
                handle_sync_message(data[1:], self.room.doc)
            else:
                self.room.track_awareness(sender, data)
        await self.send(bytes_data=data)
