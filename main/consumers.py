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
            message = json.loads(text_data)
            from_channel = self.channel_name
            
            if message.get('type') == 'join' or message.get('type') == 'leave':
                call = message.get('type')
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'user_action',
                        'username': message.get('username'),
                        'from_channel': from_channel,
                        'action': call
                    }
                )
            else:
                
                await self.channel_layer.group_send(
                    self.group_name,
                    {
                        'type': 'chat_message',
                        'message': message,
                        'from_channel': from_channel,
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
            from_channel = event.get('from_channel')
            # Send the message to all group members except the sender
            if from_channel != self.channel_name:
                await self.send(text_data=json.dumps(message))
        except Exception as e:
            print(f"Error during sending message: {e}")

    async def user_action(self, event):
        try:
            username = event['username']
            from_channel = event.get('from_channel')
            action = event.get('action')
            
            if from_channel != self.channel_name:
                await self.send(text_data=json.dumps({
                    'type': action,
                    'username': username
                }))
        except Exception as e:
            print(f"Error during sending join notification: {e}")
