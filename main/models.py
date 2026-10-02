from django.db import models


class RoomDocument(models.Model):
    """Persisted Yjs state of a room, so a document survives everyone leaving."""

    room = models.CharField(max_length=64, unique=True)
    state = models.BinaryField()
    compressed = models.BooleanField(default=False)  # rows saved before compression hold raw updates
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.room
