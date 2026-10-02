from django.contrib import admin

from .models import RoomDocument


@admin.register(RoomDocument)
class RoomDocumentAdmin(admin.ModelAdmin):
    list_display = ('room', 'updated_at')
