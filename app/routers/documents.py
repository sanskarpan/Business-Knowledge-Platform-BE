import os
import uuid
import json
import aiofiles
from typing import List, Optional
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Document, DocumentChunk, UserActivity
from app.schemas import Document as DocumentSchema, DocumentDetail
from app.security import get_current_user
from app.config import settings
from app.utils.file_processor import (validate_file, extract_text_content, chunk_text, get_file_metadata)
from app.services.vector_service import VectorService

router = APIRouter()
vector_service = VectorService()

@router.post("/upload", response_model=DocumentSchema)
async def upload_document(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Read file content
    file_content = await file.read()
    
    # Validate file
    is_valid, error_message = validate_file(file_content, file.filename)
    if not is_valid:
        raise HTTPException(status_code=400, detail=error_message)
    
    # Generate unique filename
    file_ext = os.path.splitext(file.filename)[1]
    unique_filename = f"{uuid.uuid4()}{file_ext}"
    file_path = os.path.join(settings.upload_dir, unique_filename)

    os.makedirs(settings.upload_dir, exist_ok=True)
    
    # Save file
    async with aiofiles.open(file_path, 'wb') as f:
        await f.write(file_content)
    
    # Extract text content
    file_type = file.content_type
    text_content = extract_text_content(file_path, file_type)
    
    # Get file metadata
    metadata = get_file_metadata(file_path, file_content)
    
    # Create document record
    db_document = Document(
        user_id=current_user.id,
        filename=unique_filename,
        original_filename=file.filename,
        content=text_content,
        file_path=file_path,
        file_size=len(file_content),
        file_type=file_type,
        doc_metadata=json.dumps(metadata)
    )
    
    db.add(db_document)
    db.commit()
    db.refresh(db_document)
    
    # Create text chunks and embeddings
    if text_content and text_content.strip():
        chunks = chunk_text(text_content)
        for i, chunk in enumerate(chunks):
            # Create embedding using vector service
            try:
                embedding = await vector_service.create_embedding(chunk)
                
                # Store chunk in database
                db_chunk = DocumentChunk(
                    document_id=db_document.id,
                    content=chunk,
                    embedding=json.dumps(embedding) if embedding else None,
                    position=i
                )
                db.add(db_chunk)
                
                # Store in Pinecone if embedding was created
                if embedding:
                    vector_data = {
                        'id': str(db_chunk.id),
                        'values': embedding,
                        'metadata': {
                            'document_id': db_document.id,
                            'user_id': current_user.id,
                            'filename': file.filename,
                            'chunk_position': i
                        }
                    }
                    await vector_service.store_vectors([vector_data])
                    
            except Exception as e:
                print(f"Error creating embedding for chunk {i}: {e}")
                # Store chunk without embedding
                db_chunk = DocumentChunk(
                    document_id=db_document.id,
                    content=chunk,
                    embedding=None,
                    position=i
                )
                db.add(db_chunk)
        
        db.commit()
    
    # Log activity
    activity = UserActivity(
        user_id=current_user.id,
        action="upload",
        resource_id=str(db_document.id),
        details=json.dumps({
            "filename": file.filename, 
            "file_size": len(file_content),
            "chunks_created": len(chunks) if text_content else 0
        })
    )
    db.add(activity)
    db.commit()
    
    return db_document

# Continue with rest of documents router endpoints...
@router.get("/", response_model=List[DocumentSchema])
async def get_documents(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    search: Optional[str] = Query(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query = db.query(Document).filter(Document.user_id == current_user.id)
    
    if search:
        query = query.filter(Document.original_filename.contains(search))
    
    documents = query.offset(skip).limit(limit).all()
    return documents

@router.get("/{document_id}", response_model=DocumentDetail)
async def get_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document

@router.delete("/{document_id}")
async def delete_document(
    document_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Delete file from filesystem
    try:
        if os.path.exists(document.file_path):
            os.remove(document.file_path)
    except Exception as e:
        print(f"Error deleting file {document.file_path}: {e}")
    
    # Delete vectors from Pinecone
    try:
        chunks = db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).all()
        chunk_ids = [str(chunk.id) for chunk in chunks]
        if chunk_ids:
            await vector_service.delete_vectors(chunk_ids)
    except Exception as e:
        print(f"Error deleting vectors: {e}")
    
    # Delete document chunks
    db.query(DocumentChunk).filter(DocumentChunk.document_id == document_id).delete()
    
    # Delete document
    db.delete(document)
    db.commit()
    
    # Log activity
    activity = UserActivity(
        user_id=current_user.id,
        action="delete",
        resource_id=str(document_id),
        details=json.dumps({"filename": document.original_filename})
    )
    db.add(activity)
    db.commit()
    
    return {"message": "Document deleted successfully"}
