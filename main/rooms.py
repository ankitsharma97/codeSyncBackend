import asyncio
import logging

from channels.db import database_sync_to_async
from django.utils import timezone
from pycrdt import Doc

from . import awareness
from .models import RoomDocument

logger = logging.getLogger(__name__)

SAVE_DELAY = 2  # seconds to batch edits before writing to the DB


class Room:
    """Per-process state for one collaborative document."""

    def __init__(self, name, doc):
        self.name = name
        self.doc = doc
        self.channels = set()  # local consumers
        self.peers = {}  # client_id -> (clock, state_json)
        self.peer_owner = {}  # channel_name -> {client_id}
        self.dirty = False
        self._save_task = None

    def track_awareness(self, channel, message):
        for client_id, clock, state in awareness.parse(message):
            if state == 'null':
                self.peers.pop(client_id, None)
                self.peer_owner.get(channel, set()).discard(client_id)
            else:
                self.peers[client_id] = (clock, state)
                self.peer_owner.setdefault(channel, set()).add(client_id)

    def awareness_snapshot(self):
        if not self.peers:
            return None
        return awareness.encode([(cid, clock, state) for cid, (clock, state) in self.peers.items()])

    def drop_channel(self, channel):
        """Forget a channel's peers and return the removal messages to broadcast."""
        removals = []
        for client_id in self.peer_owner.pop(channel, ()):
            clock, _ = self.peers.pop(client_id, (0, None))
            removals.append(awareness.removal(client_id, clock))
        return removals

    def mark_dirty(self):
        self.dirty = True
        if self._save_task is None:
            self._save_task = asyncio.ensure_future(self._save_later())

    async def _save_later(self):
        try:
            await asyncio.sleep(SAVE_DELAY)
        finally:
            self._save_task = None
        await self.save()

    async def save(self):
        if not self.dirty:
            return
        self.dirty = False
        try:
            await _store(self.name, self.doc.get_update())
        except Exception:
            self.dirty = True
            logger.exception('Failed to persist room %s', self.name)


@database_sync_to_async
def _store(name, state):
    RoomDocument.objects.update_or_create(
        room=name, defaults={'state': state, 'updated_at': timezone.now()}
    )


@database_sync_to_async
def _load(name):
    doc = Doc()
    row = RoomDocument.objects.filter(room=name).first()
    if row is not None:
        doc.apply_update(bytes(row.state))
    return doc


_rooms = {}
_lock = None


def _room_lock():
    # Created lazily: on Python < 3.10 a Lock binds to the loop that exists at creation time.
    global _lock
    if _lock is None:
        _lock = asyncio.Lock()
    return _lock


async def join(name, channel):
    async with _room_lock():
        room = _rooms.get(name)
        if room is None:
            room = _rooms[name] = Room(name, await _load(name))
        room.channels.add(channel)
        return room


async def leave(room, channel):
    # Held across the final save so a rejoining client can't load stale state.
    async with _room_lock():
        room.channels.discard(channel)
        if room.channels:
            return
        if room._save_task is not None:
            room._save_task.cancel()
        await room.save()
        _rooms.pop(room.name, None)
