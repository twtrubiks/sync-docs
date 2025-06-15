import uuid
from ninja_extra import api_controller, http_get, http_post, http_put, http_delete
from ninja import Schema
from django.shortcuts import get_object_or_404
from .models import Document
from typing import List
from ninja_jwt.authentication import JWTAuth
from ninja_extra.permissions import IsAuthenticated
from datetime import datetime
from django.contrib.auth.models import User
from django.db.models import Q
from channels.layers import get_channel_layer
import asyncio

class UserSchema(Schema):
    id: int
    username: str
    email: str

class ShareRequestSchema(Schema):
    username: str

class DocumentListSchema(Schema):
    id: uuid.UUID
    title: str
    owner: UserSchema
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False # Will be set dynamically

class DocumentSchema(Schema):
    id: uuid.UUID
    title: str
    content: dict
    owner: UserSchema
    created_at: datetime
    updated_at: datetime
    is_owner: bool = False # Will be set dynamically

class DocumentCreateSchema(Schema):
    title: str
    content: dict = None

class DocumentUpdateSchema(Schema):
    title: str = None
    content: dict = None

@api_controller("/documents", tags=["documents"], auth=JWTAuth(), permissions=[IsAuthenticated])
class DocumentController:
    @http_post("/", response=DocumentSchema)
    def create_document(self, payload: DocumentCreateSchema):
        """
        Creates a new document.
        """
        document = Document.objects.create(**payload.dict(exclude_none=True), owner=self.context.request.auth)
        document.is_owner = True # The creator is always the owner
        return document

    @http_get("/", response=List[DocumentListSchema])
    def list_documents(self):
        """
        Retrieves a list of documents owned by or shared with the user.
        """
        user = self.context.request.auth
        documents = Document.objects.select_related('owner').filter(Q(owner=user) | Q(shared_with=user)).distinct()

        # Dynamically set the is_owner flag for each document
        for doc in documents:
            doc.is_owner = (doc.owner == user)

        return documents

    @http_get("/{document_id}/", response=DocumentSchema)
    def get_document(self, document_id: uuid.UUID):
        """
        Retrieves a specific document by its ID, if the user has access.
        """
        user = self.context.request.auth
        query = Q(owner=user) | Q(shared_with=user)
        document = get_object_or_404(Document.objects.select_related('owner'), Q(id=document_id) & query)

        # Dynamically set the is_owner flag
        document.is_owner = (document.owner == user)

        return document

    @http_put("/{document_id}/", response=DocumentSchema)
    def update_document(self, document_id: uuid.UUID, payload: DocumentUpdateSchema):
        """
        Updates a specific document, if the user has access.
        Also broadcasts the update to collaborators.
        """
        user = self.context.request.auth
        query = Q(owner=user) | Q(shared_with=user)
        document = get_object_or_404(Document.objects.select_related('owner'), Q(id=document_id) & query)

        for attr, value in payload.dict(exclude_unset=True).items():
            setattr(document, attr, value)
        document.save()

        # Broadcast the save event to the document's channel group
        channel_layer = get_channel_layer()
        room_group_name = f'doc_{document.id}'

        # Use asyncio to run the async channel_layer.group_send in a sync context
        asyncio.run(
            channel_layer.group_send(
                room_group_name,
                {
                    "type": "doc_saved",
                    "updated_at": document.updated_at.isoformat(),
                },
            )
        )

        # Dynamically set the is_owner flag
        document.is_owner = (document.owner == user)

        return document

    @http_delete("/{document_id}/")
    def delete_document(self, document_id: uuid.UUID):
        """
        Deletes a specific document.
        """
        document = get_object_or_404(Document, id=document_id, owner=self.context.request.auth)
        document.delete()
        return {"success": True}

    @http_get("/{document_id}/collaborators/", response=List[UserSchema])
    def get_collaborators(self, document_id: uuid.UUID):
        """
        Gets the list of collaborators for a document. Only owner can access.
        """
        document = get_object_or_404(Document, id=document_id, owner=self.context.request.auth)
        return document.shared_with.all()

    @http_post("/{document_id}/collaborators/", response=UserSchema)
    def add_collaborator(self, document_id: uuid.UUID, payload: ShareRequestSchema):
        """
        Adds a collaborator to a document. Only owner can add.
        """
        document = get_object_or_404(Document, id=document_id, owner=self.context.request.auth)
        user_to_add = get_object_or_404(User, username=payload.username)
        document.shared_with.add(user_to_add)
        return user_to_add

    @http_delete("/{document_id}/collaborators/{user_id}/")
    def remove_collaborator(self, document_id: uuid.UUID, user_id: int):
        """
        Removes a collaborator from a document. Only owner can remove.
        """
        document = get_object_or_404(Document, id=document_id, owner=self.context.request.auth)
        user_to_remove = get_object_or_404(User, id=user_id)
        document.shared_with.remove(user_to_remove)
        return {"success": True}
