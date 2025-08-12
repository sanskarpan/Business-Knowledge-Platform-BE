import asyncio
from typing import List, Dict, Optional, Any
from openai import OpenAI
from openai import AsyncOpenAI
from app.config import settings

class AIService:
    def __init__(self):
        try:
            self.client = OpenAI(api_key=settings.openai_api_key)
            self.async_client = AsyncOpenAI(api_key=settings.openai_api_key)
            print("AI service initialized successfully")
        except Exception as e:
            print(f"AI service initialization failed: {e}")
            self.client = None
            self.async_client = None
    
    async def generate_response(
        self, 
        query: str, 
        context_chunks: List[str], 
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Generate AI response using OpenAI GPT"""
        if not self.client:
            return {
                "response": "AI service is not available. Please check your OpenAI API key.",
                "error": "OpenAI client not initialized"
            }
        
        try:
            # Prepare context
            context = "\n\n".join(context_chunks) if context_chunks else ""
            
            # Prepare conversation history
            messages = []
            if conversation_history:
                messages.extend(conversation_history[-10:])  # Last 10 messages for context
            
            # System message
            system_message = f"""You are a helpful AI assistant that answers questions based on the provided context from documents. 
            
Context from documents:
{context}

Instructions:
- Answer questions based on the provided context
- If the context doesn't contain relevant information, say so clearly
- Provide specific references to the source material when possible
- Be concise but comprehensive
- If asked about something not in the context, explain that you can only answer based on the provided documents
"""
            
            messages.insert(0, {"role": "system", "content": system_message})
            messages.append({"role": "user", "content": query})
            
            # Generate response
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="gpt-4",
                messages=messages,
                max_tokens=1000,
                temperature=0.7
            )
            
            ai_response = response.choices[0].message.content
            
            return {
                "response": ai_response,
                "model": "gpt-4",
                "tokens_used": response.usage.total_tokens
            }
            
        except Exception as e:
            print(f"Error generating AI response: {e}")
            return {
                "response": "I apologize, but I'm having trouble generating a response right now. Please try again later.",
                "error": str(e)
            }

    async def stream_response(
        self,
        query: str,
        context_chunks: List[str],
        conversation_history: Optional[List[Dict]] = None,
        model: str = "gpt-4",
        temperature: float = 0.7,
        max_tokens: int = 1000,
    ):
        """Async generator that yields streamed tokens from OpenAI."""
        if not self.async_client:
            data = await self.generate_response(query, context_chunks, conversation_history)
            yield data.get("response", "")
            return

        context = "\n\n".join(context_chunks) if context_chunks else ""
        messages = []
        if conversation_history:
            messages.extend(conversation_history[-10:])
        system_message = f"""You are a helpful AI assistant that answers questions based on the provided context from documents.

Context from documents:
{context}

Instructions:
- Answer questions based on the provided context
- If the context doesn't contain relevant information, say so clearly
- Provide specific references to the source material when possible
- Be concise but comprehensive
- If asked about something not in the context, explain that you can only answer based on the provided documents
"""
        messages.insert(0, {"role": "system", "content": system_message})
        messages.append({"role": "user", "content": query})

        try:
            stream = await self.async_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens,
                temperature=temperature,
                stream=True,
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta and getattr(delta, "content", None):
                    yield delta.content
        except Exception as e:
            print(f"Error streaming AI response: {e}")
            data = await self.generate_response(query, context_chunks, conversation_history)
            yield data.get("response", "")
    
    async def generate_summary(self, text: str, max_length: int = 200) -> str:
        """Generate a summary of the provided text"""
        if not self.client:
            return "AI service not available for summarization."
            
        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system", 
                        "content": f"Summarize the following text in no more than {max_length} words. Be concise and capture the key points."
                    },
                    {"role": "user", "content": text}
                ],
                max_tokens=max_length * 2,
                temperature=0.3
            )
            
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error generating summary: {e}")
            return "Unable to generate summary at this time."
    
    async def extract_keywords(self, text: str, max_keywords: int = 10) -> List[str]:
        """Extract keywords from text"""
        if not self.client:
            return []
            
        try:
            response = await asyncio.to_thread(
                self.client.chat.completions.create,
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system", 
                        "content": f"Extract up to {max_keywords} important keywords or phrases from the following text. Return them as a comma-separated list."
                    },
                    {"role": "user", "content": text}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            keywords_text = response.choices[0].message.content
            keywords = [kw.strip() for kw in keywords_text.split(',')]
            return keywords[:max_keywords]
        except Exception as e:
            print(f"Error extracting keywords: {e}")
            return []