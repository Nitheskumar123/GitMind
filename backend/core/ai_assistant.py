import time
import logging
from groq import AsyncGroq 
from django.conf import settings
from asgiref.sync import sync_to_async
from .prompts import (
    get_system_prompt,
    build_repositories_context,
    build_specific_query_context
)

logger = logging.getLogger(__name__)

class GroqAssistant:
    def __init__(self, user):
        self.user = user
        self.client = AsyncGroq(api_key=settings.GROQ_API_KEY)
        self.model = settings.GROQ_MODEL
        self.max_tokens = settings.GROQ_MAX_TOKENS

    async def get_streaming_response(self, user_message, conversation_history=None):
        """
        Stream the response asynchronously from Groq
        """
        start_time = time.time()
        full_content = ""

        try:
            # Wrap synchronous DB calls with sync_to_async
            repositories_context = await sync_to_async(build_repositories_context)(self.user)
            specific_context = await sync_to_async(build_specific_query_context)(
                self.user, user_message.lower()
            )
            
            full_context = repositories_context
            if specific_context:
                full_context += "\n\n" + specific_context

            system_prompt = get_system_prompt(self.user, full_context)

            messages = [{"role": "system", "content": system_prompt}]
            if conversation_history:
                for msg in conversation_history[-10:]:
                    messages.append({"role": msg.role, "content": msg.content})
            messages.append({"role": "user", "content": user_message})

            # 3. Add 'await' before the create call
            stream = await self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=self.max_tokens,
                temperature=0.7,
                stream=True,
            )

            # 4. Use 'async for' to iterate over the stream
            async for chunk in stream:
                if chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    full_content += content
                    yield {
                        'type': 'content',
                        'content': content
                    }

            estimated_tokens = len(full_content.split()) * 1.3  # ~1.3 tokens per word
            yield {
                'type': 'complete',
                'full_content': full_content,
                'tokens_used': int(estimated_tokens),
                'processing_time': time.time() - start_time
            }

        except Exception as e:
            logger.error(f"Streaming error: {e}")
            yield {
                'type': 'error',
                'content': f"AI Streaming Error: {str(e)}"
            }