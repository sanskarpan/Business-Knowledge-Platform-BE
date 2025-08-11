from pydantic import BaseModel, EmailStr
from typing import Optional, List, Any
from datetime import datetime

# User schemas
class UserBase(BaseModel):
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserLogin(UserBase):
    password: str

class User(UserBase):
    id: int
    role: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

# Document schemas
class DocumentBase(BaseModel):
    filename: str

class DocumentCreate(DocumentBase):
    pass

class Document(DocumentBase):
    id: int
    user_id: int
    original_filename: str
    file_size: int
    file_type: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class DocumentDetail(Document):
    content: Optional[str] = None
    metadata: Optional[str] = None

# Chat schemas
class ChatSessionCreate(BaseModel):
    title: Optional[str] = "New Conversation"

class ChatSession(BaseModel):
    id: int
    user_id: int
    title: str
    created_at: datetime
    
    class Config:
        from_attributes = True

class ChatMessageCreate(BaseModel):
    content: str

class ChatMessage(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    sources: Optional[str] = None
    timestamp: datetime
    
    class Config:
        from_attributes = True

class ChatResponse(BaseModel):
    message: str
    sources: Optional[List[dict]] = None

# Search schemas
class SearchQuery(BaseModel):
    query: str
    limit: Optional[int] = 10

class SearchResult(BaseModel):
    document_id: int
    filename: str
    content_snippet: str
    relevance_score: float

# Analytics schemas
class UsageAnalytics(BaseModel):
    total_documents: int
    total_searches: int
    total_chat_sessions: int
    recent_activities: List[dict]

class DocumentAnalytics(BaseModel):
    total_documents: int
    documents_by_type: dict
    recent_uploads: List[dict]
    