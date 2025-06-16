import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from django.contrib.auth.models import User
from .models import Document
from django.db.models import Q

class DocConsumer(AsyncWebsocketConsumer):
    @database_sync_to_async
    def has_permission(self, user, document_id):
        """
        Checks if a user has permission to access a document.
        """
        if not user.is_authenticated:
            return False
        try:
            # Check if the user is the owner or a collaborator
            query = Q(owner=user) | Q(shared_with=user)
            return Document.objects.filter(Q(id=document_id) & query).exists()
        except Document.DoesNotExist:
            return False

    async def connect(self):
        self.document_id = self.scope['url_route']['kwargs']['document_id']
        self.room_group_name = f'doc_{self.document_id}'
        self.user = self.scope.get('user')

        # Check permissions
        if self.user and await self.has_permission(self.user, self.document_id):
            # Join room group
            await self.channel_layer.group_add(
                self.room_group_name,
                self.channel_name
            )
            await self.accept()
        else:
            # Reject the connection
            await self.close()

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    # Receive message from WebSocket
    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        delta = text_data_json['delta']

        # Broadcast the delta to other users in the group for real-time editing
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'doc_update',
                'delta': delta,
                'sender_channel': self.channel_name
            }
        )

    # Receive doc_update message from room group
    async def doc_update(self, event):
        delta = event['delta']
        sender_channel = event.get('sender_channel')

        # Send delta to WebSocket, but not back to the original sender
        if self.channel_name != sender_channel:
            await self.send(text_data=json.dumps({
                'type': 'doc_update',
                'delta': delta
            }))

    # Receive doc_saved message from room group (sent from API on save)
    async def doc_saved(self, event):
        updated_at = event['updated_at']

        # Send the new timestamp to everyone in the group
        await self.send(text_data=json.dumps({
            'type': 'doc_saved',
            'updated_at': updated_at
        }))
