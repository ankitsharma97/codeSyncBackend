from django.urls import path
from .consumers import CodeSyncConsumer

ws_urlpatterns = [
    path('ws/code_sync/<str:grp>/', CodeSyncConsumer.as_asgi())
]