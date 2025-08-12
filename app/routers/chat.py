import json
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, ChatSession, ChatMessage, DocumentChunk, UserActivity
from app.schemas import (
    ChatSessionCreate, ChatSession as ChatSessionSchema,
    ChatMessageCreate, ChatMessage as ChatMessageSchema,
    ChatResponse
)
from app.security import get_current_user
from app.services.vector_service import VectorService
from app.services.ai_service import AIService
import asyncio
from datetime import datetime

router = APIRouter()
vector_service = VectorService()
ai_service = AIService()

@router.post("/sessions", response_model=ChatSessionSchema)
async def create_chat_session(
    session: ChatSessionCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Create a new chat session"""
    db_session = ChatSession(
        user_id=current_user.id,
        title=session.title
    )
    db.add(db_session)
    db.commit()
    db.refresh(db_session)
    
    # Log activity
    activity = UserActivity(
        user_id=current_user.id,
        action="create_session",
        resource_id=str(db_session.id),
        details=json.dumps({"title": session.title})
    )
    db.add(activity)
    db.commit()
    
    return db_session

@router.get("/sessions", response_model=List[ChatSessionSchema])
async def get_chat_sessions(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get all chat sessions for the current user"""
    sessions = db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id
    ).order_by(ChatSession.created_at.desc()).all()
    
    return sessions

@router.get("/sessions/{session_id}/messages", response_model=List[ChatMessageSchema])
async def get_chat_history(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get chat history for a specific session"""
    # Verify session belongs to user
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    messages = db.query(ChatMessage).filter(
        ChatMessage.session_id == session_id
    ).order_by(ChatMessage.timestamp.asc()).all()
    
    return messages

@router.post("/sessions/{session_id}/messages", response_model=ChatResponse)
async def send_message(
    session_id: int,
    message: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Send a message and get AI response"""
    # Verify session belongs to user
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    # Store user message
    user_message = ChatMessage(
        session_id=session_id,
        role="user",
        content=message.content
    )
    db.add(user_message)
    db.commit()
    
    try:
        # Create embedding for the query
        query_embedding = await vector_service.create_embedding(message.content)
        
        # Search for relevant document chunks
        relevant_chunks = []
        source_documents = []
        
        if query_embedding:
            # Search in vector database
            search_results = await vector_service.search_similar(
                query_embedding,
                top_k=5,
                filter_dict={"user_id": current_user.id}
            )
            
            # Get the actual document chunks
            for result in search_results:
                raw_id = result.get('id')
                try:
                    chunk_id = int(raw_id)
                except (TypeError, ValueError):
                    continue
                chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
                
                if chunk:
                    relevant_chunks.append(chunk.content)
                    # Get document info for sources
                    doc = chunk.document
                    if doc not in source_documents:
                        source_documents.append({
                            "id": doc.id,
                            "filename": doc.original_filename,
                            "relevance_score": result['score']
                        })
        
        # Get conversation history for context
        recent_messages = db.query(ChatMessage).filter(
            ChatMessage.session_id == session_id
        ).order_by(ChatMessage.timestamp.desc()).limit(10).all()
        
        conversation_history = []
        for msg in reversed(recent_messages):
            conversation_history.append({
                "role": msg.role,
                "content": msg.content
            })
        
        # Generate AI response
        ai_response_data = await ai_service.generate_response(
            query=message.content,
            context_chunks=relevant_chunks,
            conversation_history=conversation_history
        )
        
        ai_response_text = ai_response_data.get("response", "I apologize, but I couldn't generate a response.")
        
        # Store AI response
        ai_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content=ai_response_text,
            sources=json.dumps(source_documents) if source_documents else None
        )
        db.add(ai_message)
        db.commit()
        
        # Log activity
        activity = UserActivity(
            user_id=current_user.id,
            action="chat",
            resource_id=str(session_id),
            details=json.dumps({
                "message_length": len(message.content),
                "sources_found": len(source_documents)
            })
        )
        db.add(activity)
        db.commit()
        
        return ChatResponse(
            message=ai_response_text,
            sources=source_documents
        )
        
    except Exception as e:
        print(f"Error processing message: {e}")
        db.rollback()
        # Store error response
        error_message = ChatMessage(
            session_id=session_id,
            role="assistant",
            content="I apologize, but I encountered an error while processing your message. Please try again."
        )
        db.add(error_message)
        db.commit()
        
        return ChatResponse(
            message="I apologize, but I encountered an error while processing your message. Please try again.",
            sources=[]
        )

@router.delete("/sessions/{session_id}")
async def delete_chat_session(
    session_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Delete a chat session and all its messages"""
    # Verify session belongs to user
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    # Delete all messages in the session
    db.query(ChatMessage).filter(ChatMessage.session_id == session_id).delete()
    
    # Delete the session
    db.delete(session)
    db.commit()
    
    return {"message": "Chat session deleted successfully"}

@router.put("/sessions/{session_id}/title")
async def update_session_title(
    session_id: int,
    title_update: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Update chat session title"""
    session = db.query(ChatSession).filter(
        ChatSession.id == session_id,
        ChatSession.user_id == current_user.id
    ).first()
    
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found")
    
    session.title = title_update.get("title", session.title)
    db.commit()
    db.refresh(session)
    
    return session

# Streaming endpoint for real-time responses (optional enhancement)
@router.post("/sessions/{session_id}/stream")
async def stream_message(
    session_id: int,
    message: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Stream AI response in real-time"""
    async def generate_stream():
        try:
            # Similar logic to send_message but with streaming
            # This is a placeholder for streaming implementation
            yield f"data: {json.dumps({'type': 'start', 'content': ''})}\n\n"
            
            # Process message (similar to above)
            # Reuse generation but avoid duplicate DB writes by calling AI service directly
            query_embedding = await vector_service.create_embedding(message.content)
            relevant_chunks = []
            if query_embedding:
                results = await vector_service.search_similar(query_embedding, top_k=5, filter_dict={"user_id": current_user.id})
                for r in results:
                    try:
                        cid = int(r.get('id'))
                    except (TypeError, ValueError):
                        continue
                    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == cid).first()
                    if chunk:
                        relevant_chunks.append(chunk.content)

            recent = db.query(ChatMessage).filter(ChatMessage.session_id == session_id).order_by(ChatMessage.timestamp.desc()).limit(10).all()
            history = [{"role": m.role, "content": m.content} for m in reversed(recent)]
            ai_data = await ai_service.generate_response(query=message.content, context_chunks=relevant_chunks, conversation_history=history)
            text = ai_data.get("response", "")
            # Tokenize by words to stream
            words = text.split()
            # Stream the response word by word for demonstration
            
            for word in words:
                yield f"data: {json.dumps({'type': 'token', 'content': word + ' '})}\n\n"
                await asyncio.sleep(0.1)  # Simulate streaming delay
            
            yield f"data: {json.dumps({'type': 'end', 'sources': []})}\n\n"
            
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
    
    return StreamingResponse(
        generate_stream(),
        media_type="text/plain",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
