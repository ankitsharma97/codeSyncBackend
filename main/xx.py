from channels.generic.websocket import AsyncWebsocketConsumer
import json

class CodeSyncConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = self.scope['url_route']['kwargs']['grp']
        await self.channel_layer.group_add(
            self.group_name,
            self.channel_name
        )
        await self.accept()

    async def receive(self, text_data):
        try:
            message = text_data
            print(f"Message received: {message}")
            await self.channel_layer.group_send(
                self.group_name,
                {
                    'type': 'chat_message',
                    'message': message
                }
            )
        except json.JSONDecodeError as e:
            print(f"JSON decode error: {e}")
        except KeyError as e:
            print(f"KeyError: {e}")
        except Exception as e:
            print(f"Error during message receive: {e}")

    async def disconnect(self, close_code):
        try:
            await self.channel_layer.group_discard(
                self.group_name,
                self.channel_name
            )
        except Exception as e:
            print(f"Error during disconnect: {e}")

    async def chat_message(self, event):
        try:
            message = event['message']
            await self.send(text_data=message)
        except Exception as e:
            print(f"Error during sending message: {e}")
