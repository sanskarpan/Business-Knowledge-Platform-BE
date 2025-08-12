import asyncio
from typing import List, Optional, Dict, Any
from pinecone import Pinecone, ServerlessSpec
from openai import OpenAI
from app.config import settings

class VectorService:
    def __init__(self):
        try:
            # Initialize Pinecone with new API
            self.pc = Pinecone(api_key=settings.pinecone_api_key)
            
            # Initialize OpenAI (new SDK client)
            self.openai_client = OpenAI(api_key=settings.openai_api_key)
            
            # Index name
            self.index_name = "knowledge-platform"
            
            # Create index if it doesn't exist
            self._ensure_index_exists()
            
            # Get index
            self.index = self.pc.Index(self.index_name)
            
            print("Vector service initialized successfully")
            
        except Exception as e:
            print(f"Vector service initialization failed: {e}")
            print("Will continue without vector search functionality")
            self.pc = None
            self.index = None
            self.openai_client = None
    
    def _ensure_index_exists(self):
        """Create Pinecone index if it doesn't exist"""
        try:
            # Check if index exists (Pinecone >= 4 uses list_indexes returning list[str])
            existing_indexes = self.pc.list_indexes()
            index_names = list(existing_indexes) if existing_indexes else []
            
            if self.index_name not in index_names:
                print(f"Creating Pinecone index: {self.index_name}")
                
                # Create index with serverless spec
                self.pc.create_index(
                    name=self.index_name,
                    dimension=1536,
                    metric="cosine",
                    spec=ServerlessSpec(cloud="aws", region="us-east-1"),
                )
                # Wait until ready
                print("Waiting for index to be ready...")
                import time
                for _ in range(60):
                    status = self.pc.describe_index(self.index_name)
                    if getattr(status, "status", {}).get("ready", False):
                        break
                    time.sleep(2)
                print("Index created successfully")
            else:
                print(f"Index {self.index_name} already exists")
                
        except Exception as e:
            print(f"Error managing Pinecone index: {e}")
            print("Index already created")
            # print("You may need to create the index manually in Pinecone console")
    
    async def create_embedding(self, text: str) -> Optional[List[float]]:
        """Create embedding for text using OpenAI"""
        if not self.openai_client:
            print("OpenAI client not initialized")
            return None
            
        try:
            response = await asyncio.to_thread(
                self.openai_client.embeddings.create,
                input=text,
                model="text-embedding-ada-002"
            )
            return response.data[0].embedding
        except Exception as e:
            print(f"Error creating embedding: {e}")
            return None
    
    async def store_vectors(self, vectors: List[Dict[str, Any]]) -> bool:
        """Store vectors in Pinecone"""
        if not self.index:
            print("Pinecone index not available")
            return False
            
        try:
            # Format vectors for new API
            formatted_vectors = []
            for vector in vectors:
                formatted_vectors.append({
                    "id": str(vector["id"]),
                    "values": vector["values"],
                    "metadata": vector.get("metadata", {})
                })
            
            # Upsert vectors to Pinecone
            await asyncio.to_thread(self.index.upsert, vectors=formatted_vectors)
            return True
        except Exception as e:
            print(f"Error storing vectors: {e}")
            return False
    
    async def search_similar(self, query_embedding: List[float], top_k: int = 5, filter_dict: Optional[Dict] = None) -> List[Dict]:
        """Search for similar vectors"""
        if not self.index:
            print("Pinecone index not available")
            return []
            
        try:
            search_results = await asyncio.to_thread(
                self.index.query,
                vector=query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=filter_dict
            )
            
            results = []
            for match in search_results.matches:
                results.append({
                    'id': match.id,
                    'score': match.score,
                    'metadata': match.metadata or {}
                })
            
            return results
        except Exception as e:
            print(f"Error searching vectors: {e}")
            return []
    
    async def delete_vectors(self, ids: List[str]) -> bool:
        """Delete vectors from Pinecone"""
        if not self.index:
            print("Pinecone index not available")
            return False
            
        try:
            await asyncio.to_thread(self.index.delete, ids=ids)
            return True
        except Exception as e:
            print(f"Error deleting vectors: {e}")
            return False