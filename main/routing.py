from django.urls import re_path

from .consumers import CodeSyncConsumer

# y-websocket appends the room name to the base URL without a trailing slash.
ws_urlpatterns = [
    re_path(r'^ws/code_sync/(?P<room>[A-Za-z0-9_-]{1,64})/?$', CodeSyncConsumer.as_asgi()),
]
