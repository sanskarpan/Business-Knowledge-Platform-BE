import pinecone
import openai
from typing import List, Optional, Dict, Any
from app.config import settings
import json
import asyncio

class VectorService:
    def __init__(self):
        # Initialize Pinecone
        pinecone.init(
            api_key=settings.pinecone_api_key,
            environment=settings.pinecone_environment
        )
        
        # Initialize OpenAI
        openai.api_key = settings.openai_api_key
        
        # Index name
        self.index_name = "knowledge-platform"
        
        # Create index if it doesn't exist
        self._ensure_index_exists()
        
        # Get index
        self.index = pinecone.Index(self.index_name)
    
    def _ensure_index_exists(self):
        """Create Pinecone index if it doesn't exist"""
        try:
            existing_indexes = pinecone.list_indexes()
            if self.index_name not in existing_indexes:
                pinecone.create_index(
                    name=self.index_name,
                    dimension=1536,  # OpenAI ada-002 embedding dimension
                    metric="cosine"
                )
                # Wait for index to be ready
                import time
                time.sleep(60)
        except Exception as e:
            print(f"Error ensuring index exists: {e}")
    
    async def create_embedding(self, text: str) -> Optional[List[float]]:
        """Create embedding for text using OpenAI"""
        try:
            response = await asyncio.to_thread(
                openai.Embedding.create,
                input=text,
                model="text-embedding-ada-002"
            )
            return response['data'][0]['embedding']
        except Exception as e:
            print(f"Error creating embedding: {e}")
            return None
    
    async def store_vectors(self, vectors: List[Dict[str, Any]]) -> bool:
        """Store vectors in Pinecone"""
        try:
            # Upsert vectors to Pinecone
            await asyncio.to_thread(self.index.upsert, vectors=vectors)
            return True
        except Exception as e:
            print(f"Error storing vectors: {e}")
            return False
    
    async def search_similar(self, query_embedding: List[float], top_k: int = 5, filter_dict: Optional[Dict] = None) -> List[Dict]:
        """Search for similar vectors"""
        try:
            search_results = await asyncio.to_thread(
                self.index.query,
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=filter_dict
            )
            
            results = []
            for match in search_results['matches']:
                results.append({
                    'id': match['id'],
                    'score': match['score'],
                    'metadata': match.get('metadata', {})
                })
            
            return results
        except Exception as e:
            print(f"Error searching vectors: {e}")
            return []
    
    async def delete_vectors(self, ids: List[str]) -> bool:
        """Delete vectors from Pinecone"""
        try:
            await asyncio.to_thread(self.index.delete, ids=ids)
            return True
        except Exception as e:
            print(f"Error deleting vectors: {e}")
            return False

# File: app/services/ai_service.py
import openai
from typing import List, Dict, Optional
from app.config import settings
import json

class AIService:
    def __init__(self):
        openai.api_key = settings.openai_api_key
    
    async def generate_response(
        self, 
        query: str, 
        context_chunks: List[str], 
        conversation_history: Optional[List[Dict]] = None
    ) -> Dict[str, Any]:
        """Generate AI response using OpenAI GPT"""
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
                openai.ChatCompletion.create,
                model="gpt-4",
                messages=messages,
                max_tokens=1000,
                temperature=0.7,
                stream=False
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
    
    async def generate_summary(self, text: str, max_length: int = 200) -> str:
        """Generate a summary of the provided text"""
        try:
            response = await asyncio.to_thread(
                openai.ChatCompletion.create,
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
        try:
            response = await asyncio.to_thread(
                openai.ChatCompletion.create,
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