"""
WebSocket consumers for real-time chat
"""

import json
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.db import database_sync_to_async
from .models import User, Conversation, ChatMessage
from .ai_assistant import GroqAssistant
import logging

logger = logging.getLogger(__name__)


class ChatConsumer(AsyncWebsocketConsumer):
    """
    WebSocket consumer for AI chat
    """
    
    async def connect(self):
        """
        Handle WebSocket connection
        """
        self.user = self.scope['user']
        
        # Check if user is authenticated
        if not self.user.is_authenticated:
            await self.close()
            return
        
        # Accept connection
        await self.accept()
        
        logger.info(f"WebSocket connected for user: {self.user.github_login}")
        
        # Send connection confirmation
        await self.send(text_data=json.dumps({
            'type': 'connection',
            'message': 'Connected to AI Assistant',
            'user': self.user.github_login
        }))
    
    async def disconnect(self, close_code):
        """
        Handle WebSocket disconnection
        """
        logger.info(f"WebSocket disconnected for user: {self.user.github_login}")
    
    async def receive(self, text_data):
        """
        Handle incoming messages from WebSocket
        """
        try:
            data = json.loads(text_data)
            message_type = data.get('type')
            
            if message_type == 'chat_message':
                await self.handle_chat_message(data)
            elif message_type == 'load_history':
                await self.handle_load_history(data)
            elif message_type == 'new_conversation':
                await self.handle_new_conversation()
            
        except json.JSONDecodeError:
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Invalid message format'
            }))
        except Exception as e:
            logger.error(f"Error in receive: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'An error occurred processing your message'
            }))
    
    async def handle_chat_message(self, data):
        """
        Handle chat message from user
        """
        user_message = data.get('message', '').strip()
        conversation_id = data.get('conversation_id')
        
        if not user_message:
            return
        
        logger.info(f"Processing message from {self.user.github_login}: {user_message[:50]}...")
        
        # Get or create conversation
        conversation = await self.get_or_create_conversation(conversation_id)
        
        # Save user message
        user_chat_message = await self.save_message(
            conversation=conversation,
            role='user',
            content=user_message
        )
        
        # Send user message confirmation
        await self.send(text_data=json.dumps({
            'type': 'user_message',
            'message': user_message,
            'message_id': user_chat_message.id,
            'conversation_id': conversation.id,
            'timestamp': user_chat_message.created_at.isoformat()
        }))
        
        # Get conversation history
        history = await self.get_conversation_history(conversation)
        
        # Create AI assistant
        assistant = GroqAssistant(self.user)
        
        # Send typing indicator
        await self.send(text_data=json.dumps({
            'type': 'typing',
            'is_typing': True
        }))
        
        # Get streaming response
        full_response = ""
        tokens_used = 0
        processing_time = 0
        
        try:
            async for chunk in assistant.get_streaming_response(user_message, history):
                if chunk['type'] == 'content':
                    # Stream content to client
                    full_response += chunk['content']
                    await self.send(text_data=json.dumps({
                        'type': 'assistant_message_chunk',
                        'content': chunk['content']
                    }))
                
                elif chunk['type'] == 'complete':
                    # Response complete
                    full_response = chunk['full_content']
                    tokens_used = chunk['tokens_used']
                    processing_time = chunk['processing_time']
                
                elif chunk['type'] == 'error':
                    # Error occurred
                    await self.send(text_data=json.dumps({
                        'type': 'error',
                        'message': chunk['content']
                    }))
                    return
            
            # Save assistant message
            assistant_message = await self.save_message(
                conversation=conversation,
                role='assistant',
                content=full_response,
                tokens_used=tokens_used,
                processing_time=processing_time
            )
            if tokens_used > 0:
                from .tasks import track_api_cost
                from asgiref.sync import sync_to_async
                await sync_to_async(track_api_cost)(
                    repository=None,
                    user=self.user,
                    action_type='chat',
                    tokens_used=tokens_used,
                )
            # Send completion
            await self.send(text_data=json.dumps({
                'type': 'assistant_message_complete',
                'message_id': assistant_message.id,
                'tokens_used': tokens_used,
                'processing_time': processing_time
            }))
            
            # Update conversation title if it's the first exchange
            await self.update_conversation_title(conversation, user_message)
            
        except Exception as e:
            logger.error(f"Error getting AI response: {e}")
            await self.send(text_data=json.dumps({
                'type': 'error',
                'message': 'Failed to get response from AI assistant'
            }))
        
        finally:
            # Stop typing indicator
            await self.send(text_data=json.dumps({
                'type': 'typing',
                'is_typing': False
            }))
    
    async def handle_load_history(self, data):
        """
        Load conversation history
        """
        conversation_id = data.get('conversation_id')
        
        if conversation_id:
            conversation = await self.get_conversation(conversation_id)
            if conversation:
                messages = await self.get_all_messages(conversation)
                await self.send(text_data=json.dumps({
                    'type': 'history',
                    'conversation_id': conversation.id,
                    'messages': messages
                }))
    
    async def handle_new_conversation(self):
        """
        Start a new conversation
        """
        conversation = await self.create_conversation()
        await self.send(text_data=json.dumps({
            'type': 'new_conversation',
            'conversation_id': conversation.id
        }))
    
    @database_sync_to_async
    def get_or_create_conversation(self, conversation_id=None):
        """
        Get existing conversation or create new one
        """
        if conversation_id:
            try:
                return Conversation.objects.get(id=conversation_id, user=self.user)
            except Conversation.DoesNotExist:
                pass
        
        # Create new conversation
        return Conversation.objects.create(
            user=self.user,
            title='New Conversation'
        )
    
    @database_sync_to_async
    def create_conversation(self):
        """
        Create new conversation
        """
        return Conversation.objects.create(
            user=self.user,
            title='New Conversation'
        )
    
    @database_sync_to_async
    def get_conversation(self, conversation_id):
        """
        Get conversation by ID
        """
        try:
            return Conversation.objects.get(id=conversation_id, user=self.user)
        except Conversation.DoesNotExist:
            return None
    
    @database_sync_to_async
    def save_message(self, conversation, role, content, tokens_used=0, processing_time=0):
        """
        Save chat message to database
        """
        return ChatMessage.objects.create(
            conversation=conversation,
            role=role,
            content=content,
            tokens_used=tokens_used,
            processing_time=processing_time
        )
    
    @database_sync_to_async
    def get_conversation_history(self, conversation):
        """
        Get conversation message history
        """
        return list(conversation.messages.all()[:50])
    
    @database_sync_to_async
    def get_all_messages(self, conversation):
        """
        Get all messages for history display
        """
        messages = conversation.messages.all()
        return [
            {
                'id': msg.id,
                'role': msg.role,
                'content': msg.content,
                'timestamp': msg.created_at.isoformat()
            }
            for msg in messages
        ]
    
    @database_sync_to_async
    def update_conversation_title(self, conversation, first_message):
        """
        Update conversation title based on first message
        """
        if conversation.title == 'New Conversation' and conversation.messages.count() <= 2:
            # Use first 50 chars of user's first message as title
            conversation.title = first_message[:50]
            conversation.save()
