# Knowledge Platform Backend

This repository is a FastAPI backend for AI-powered document management and conversational knowledge retrieval.

## Overview

This backend provides:
- **Document Management**: Upload, process, and store documents with OCR support
- **AI Integration**: OpenAI GPT-4 for chat and text-embedding-ada-002 for search
- **Vector Search**: Pinecone integration for semantic document retrieval
- **Authentication**: JWT-based user authentication and authorization
- **Analytics**: Usage tracking and document insights
- **RESTful API**: Comprehensive endpoints for all platform features

## Tech Stack

- **Framework**: FastAPI 
- **Database**: PostgreSQL with SQLAlchemy ORM
- **Vector DB**: Pinecone for semantic search
- **AI Services**: OpenAI GPT-4 and embeddings
- **Authentication**: JWT with bcrypt password hashing
- **File Processing**: PyPDF2, python-docx, Pillow (OCR)
- **Async**: Full async/await support with uvicorn

## Project Structure

```
backend/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI app setup
│   ├── config.py              # Configuration settings
│   ├── database.py            # Database connection
│   ├── models.py              # SQLAlchemy models
│   ├── schemas.py             # Pydantic schemas
│   ├── security.py            # Authentication utilities
│   ├── routers/
│   │   ├── auth.py           # Authentication endpoints
│   │   ├── documents.py      # Document management
│   │   ├── chat.py           # AI chat interface
│   │   ├── search.py         # Search functionality
│   │   └── analytics.py      # Analytics endpoints
│   ├── services/
│   │   ├── ai_service.py     # OpenAI integration
│   │   └── vector_service.py # Pinecone integration
│   └── utils/
│       └── file_processor.py # File processing utilities
├── uploads/                   # File storage directory
├── requirements.txt          # Python dependencies
├── .env                      # Environment variables
├── init_db.py               # Database initialization
└── README.md                # This file
```

## Quick Start

### Prerequisites
- Python 3.9+
- PostgreSQL 12+
- OpenAI API key
- Pinecone API key (optional, for vector search)

### 1. Clone and Setup
```bash
git clone https://github.com/sanskarpan/Business-Knowledge-Platform-BE.git
cd Business-Knowledge-Platform-BE.
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Environment Configuration
Create `.env` file or copy .env.sample and enter your values:
```env
# Database (Use your Supabase or local PostgreSQL URL)
DATABASE_URL=postgresql://username:password@localhost:5432/knowledge_platform

# API Keys
OPENAI_API_KEY=sk-your_openai_api_key_here
PINECONE_API_KEY=your_pinecone_api_key_here
PINECONE_ENVIRONMENT=your_pinecone_environment

# JWT Configuration
JWT_SECRET_KEY=your_super_secret_jwt_key_make_it_very_long_and_random
JWT_ALGORITHM=HS256
JWT_EXPIRE_MINUTES=1440

# File Upload
UPLOAD_DIR=./uploads
MAX_FILE_SIZE=104857600  # 100MB
```

### 4. Database Setup
```bash
# Create database (if using local PostgreSQL)
createdb knowledge_platform

# Initialize tables
python init_db.py
```

### 5. Start Development Server
```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Server will be available at:
- **API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Health Check**: http://localhost:8000/

## API Documentation

### Authentication Endpoints
```http
POST   /api/auth/register     # User registration
POST   /api/auth/login        # User login
GET    /api/auth/profile      # Get user profile
```

### Document Management
```http
POST   /api/documents/upload           # Upload document
GET    /api/documents                  # List user documents
GET    /api/documents/{id}             # Get document details
DELETE /api/documents/{id}             # Delete document
```

### Chat Interface
```http
POST   /api/chat/sessions              # Create chat session
GET    /api/chat/sessions              # List chat sessions
POST   /api/chat/sessions/{id}/messages # Send message
GET    /api/chat/sessions/{id}/messages # Get chat history
DELETE /api/chat/sessions/{id}         # Delete session
```

### Search & Knowledge
```http
GET    /api/search?q={query}           # Search documents
GET    /api/search/similar/{doc_id}    # Find similar documents
POST   /api/knowledge/ask              # Ask question about documents
```

### Analytics
```http
GET    /api/analytics/usage            # Usage statistics
GET    /api/analytics/documents        # Document analytics
GET    /api/analytics/dashboard        # Dashboard data
```

## Database Schema

### Core Tables
- **users**: User accounts and authentication
- **documents**: Document metadata and content
- **document_chunks**: Text chunks for vector search
- **chat_sessions**: Conversation sessions
- **chat_messages**: Individual chat messages
- **search_queries**: Search history
- **user_activities**: Activity logging

### Relationships
```sql
users (1) → (many) documents
documents (1) → (many) document_chunks
users (1) → (many) chat_sessions
chat_sessions (1) → (many) chat_messages
```

## Configuration Options

### File Upload Settings
```python
UPLOAD_DIR = "./uploads"           # Storage directory
MAX_FILE_SIZE = 104857600          # 100MB limit
SUPPORTED_TYPES = [".pdf", ".docx", ".txt", ".md", ".jpg", ".png"]
```

### AI Model Configuration
```python
# OpenAI Models
CHAT_MODEL = "gpt-4"                    # Main chat model
EMBEDDING_MODEL = "text-embedding-ada-002"  # Embedding model
MAX_TOKENS = 1500                       # Response length limit
TEMPERATURE = 0.7                       # Response creativity
```

### Vector Search Settings
```python
PINECONE_INDEX = "knowledge-platform"   # Index name
EMBEDDING_DIMENSION = 1536              # Vector dimensions
SIMILARITY_THRESHOLD = 0.7              # Minimum similarity score
TOP_K_RESULTS = 5                       # Max search results
```

##  Security Features

### Authentication & Authorization
- JWT tokens with configurable expiration
- bcrypt password hashing
- Protected routes with dependency injection
- User-scoped data access

### Input Validation
- Pydantic schemas for request/response validation
- File type and size restrictions
- SQL injection prevention with SQLAlchemy
- XSS protection with proper serialization

### Data Protection
- Environment variable configuration
- Secure file upload handling
- Database connection security
- API rate limiting (configurable)

## 📊 Monitoring & Logging

### Built-in Logging
```python
import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
```



## 🔧 Troubleshooting

### Common Issues

**Database Connection Error**
```bash
# Check PostgreSQL is running
pg_isready

# Verify connection string
python -c "from app.database import engine; engine.connect()"
```

**OpenAI API Error**
```bash
# Test API key
curl -H "Authorization: Bearer $OPENAI_API_KEY" \
  https://api.openai.com/v1/models
```

**File Upload Issues**
```bash
# Check upload directory permissions
chmod 755 uploads/
chown $USER:$USER uploads/
```

**Vector Search Not Working**
```bash
# Verify Pinecone configuration
python -c "from app.services.vector_service import VectorService; vs = VectorService()"
```

### Performance Issues

**Slow API Response**
- Check database query performance
- Verify vector search index status
- Review file processing performance

**Memory Usage**
- Monitor document chunk processing
- Check for memory leaks in file handling
- Optimize vector embeddings storage




