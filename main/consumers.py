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
            
            # Send the message to all group members except the sender
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
            from_channel = event.get('from_channel')  # Get the sender's channel name
            # Send the message to all group members except the sender
            if from_channel != self.channel_name:
                await self.send(text_data=json.dumps(message))
        except Exception as e:
            print(f"Error during sending message: {e}")


# from channels.generic.websocket import AsyncWebsocketConsumer
# import json

# class CodeSyncConsumer(AsyncWebsocketConsumer):
#     async def connect(self):
#         self.group_name = self.scope['url_route']['kwargs']['grp']
#         await self.channel_layer.group_add(
#             self.group_name,
#             self.channel_name
#         )
#         await self.accept()

#     async def disconnect(self, close_code):
#         await self.channel_layer.group_discard(
#             self.group_name,
#             self.channel_name
#         )
#         await self.notify_clients('disconnected')

#     async def receive(self, text_data):
#         try:
#             data = json.loads(text_data)
#             action_type = data.get('type')

#             if action_type == 'JOIN':
#                 self.username = data.get('username')
#                 await self.notify_clients('connected')
#                 await self.send_client_list()
#             elif action_type == 'LEAVE':
#                 await self.disconnect(1000)
#             elif action_type == 'CODE_CHANGE':
#                 await self.channel_layer.group_send(
#                     self.group_name,
#                     {
#                         'type': 'code_change',
#                         'message': data,
#                         'from_channel': self.channel_name,
#                     }
#                 )
#         except json.JSONDecodeError as e:
#             print(f"JSON decode error: {e}")
#         except Exception as e:
#             print(f"Error during message receive: {e}")

#     async def code_change(self, event):
#         message = event['message']
#         from_channel = event['from_channel']
#         if from_channel != self.channel_name:
#             await self.send(text_data=json.dumps(message))

#     async def notify_clients(self, action):
#         await self.channel_layer.group_send(
#             self.group_name,
#             {
#                 'type': 'client_notification',
#                 'message': {
#                     'type': action,
#                     'socketId': self.channel_name,
#                     'username': getattr(self, 'username', 'Anonymous')
#                 }
#             }
#         )

#     async def client_notification(self, event):
#         await self.send(text_data=json.dumps(event['message']))

#     async def send_client_list(self):
#         clients = []
#         for channel_name in self.channel_layer.groups.get(self.group_name, set()):
#             client = self.channel_layer.receive_buffer.get(channel_name)
#             if client:
#                 clients.append({
#                     'socketId': channel_name,
#                     'username': getattr(client.consumer, 'username', 'Anonymous')
#                 })
#         await self.channel_layer.group_send(
#             self.group_name,
#             {
#                 'type': 'client_list',
#                 'message': {
#                     'type': 'clients',
#                     'clients': clients
#                 }
#             }
#         )

#     async def client_list(self, event):
#         await self.send(text_data=json.dumps(event['message']))