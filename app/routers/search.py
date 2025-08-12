import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from datetime import datetime, date
from sqlalchemy.orm import Session
from sqlalchemy import or_, and_
from app.database import get_db
from app.models import User, Document, DocumentChunk, SearchQuery, UserActivity
from app.schemas import SearchQuery as SearchQuerySchema, SearchResult
from app.security import get_current_user
from app.services.vector_service import VectorService

router = APIRouter()
vector_service = VectorService()

@router.get("/", response_model=List[SearchResult])
async def search_documents(
    q: str = Query(..., description="Search query"),
    limit: int = Query(10, ge=1, le=50, description="Number of results to return"),
    search_type: str = Query("hybrid", description="Search type: text, semantic, or hybrid"),
    file_type: Optional[str] = Query(None, description="Filter by type: pdf|word|text|image|other"),
    date_from: Optional[date] = Query(None, description="Filter by created_at from (YYYY-MM-DD)"),
    date_to: Optional[date] = Query(None, description="Filter by created_at to (YYYY-MM-DD)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Search through documents using text and/or semantic search"""
    
    # Log search query
    search_query = SearchQuery(
        user_id=current_user.id,
        query=q
    )
    db.add(search_query)
    
    results = []
    
    # Build optional filters
    created_from_dt = datetime.combine(date_from, datetime.min.time()) if date_from else None
    created_to_dt = datetime.combine(date_to, datetime.max.time()) if date_to else None

    def _mime_types_for_category(category: str) -> List[str]:
        mapping = {
            'pdf': ['application/pdf'],
            'word': ['application/vnd.openxmlformats-officedocument.wordprocessingml.document'],
            'text': ['text/plain', 'text/markdown'],
            'image': ['image/jpeg', 'image/png', 'image/gif'],
            'other': [],
        }
        return mapping.get((category or '').lower(), [])

    if search_type in ["text", "hybrid"]:
        # Text-based search
        conditions = [Document.user_id == current_user.id]
        conditions.append(or_(Document.original_filename.contains(q), Document.content.contains(q)))
        if file_type:
            mimes = _mime_types_for_category(file_type)
            if mimes:
                conditions.append(Document.file_type.in_(mimes))
        if created_from_dt:
            conditions.append(Document.created_at >= created_from_dt)
        if created_to_dt:
            conditions.append(Document.created_at <= created_to_dt)

        text_results = db.query(Document).filter(and_(*conditions)).limit(limit).all()
        
        for doc in text_results:
            # Find relevant snippet
            content = doc.content or ""
            snippet = _extract_snippet(content, q)
            
            results.append(SearchResult(
                document_id=doc.id,
                filename=doc.original_filename,
                content_snippet=snippet,
                relevance_score=0.8  # Static score for text search
            ))
    
    if search_type in ["semantic", "hybrid"]:
        # Semantic search using embeddings
        try:
            query_embedding = await vector_service.create_embedding(q)
            if query_embedding:
                vector_results = await vector_service.search_similar(
                    query_embedding,
                    top_k=limit,
                    filter_dict={"user_id": current_user.id}
                )
                
                for result in vector_results:
                    raw_id = result.get('id')
                    try:
                        chunk_id = int(raw_id)
                    except (TypeError, ValueError):
                        # Skip invalid IDs (e.g., 'None' from legacy vectors)
                        continue
                    chunk = db.query(DocumentChunk).filter(DocumentChunk.id == chunk_id).first()
                    
                    if chunk and chunk.document:
                        # Apply file type and date filters for semantic results as well
                        if file_type:
                            mimes = _mime_types_for_category(file_type)
                            if mimes and chunk.document.file_type not in mimes:
                                continue
                        if created_from_dt and chunk.document.created_at < created_from_dt:
                            continue
                        if created_to_dt and chunk.document.created_at > created_to_dt:
                            continue
                        # Check if document already in results
                        existing = next((r for r in results if r.document_id == chunk.document.id), None)
                        if not existing:
                            results.append(SearchResult(
                                document_id=chunk.document.id,
                                filename=chunk.document.original_filename,
                                content_snippet=chunk.content[:200] + "..." if len(chunk.content) > 200 else chunk.content,
                                relevance_score=result['score']
                            ))
        except Exception as e:
            print(f"Error in semantic search: {e}")
            # Ensure session is usable after DB errors
            db.rollback()
    
    # Update search query with results count
    search_query.results_count = len(results)
    db.commit()
    
    # Log activity
    activity = UserActivity(
        user_id=current_user.id,
        action="search",
        resource_id=str(search_query.id),
        details=json.dumps({
            "query": q,
            "search_type": search_type,
            "results_count": len(results)
        })
    )
    db.add(activity)
    db.commit()
    
    # Sort by relevance score and limit results
    results.sort(key=lambda x: x.relevance_score, reverse=True)
    return results[:limit]

@router.get("/similar/{document_id}", response_model=List[SearchResult])
async def find_similar_documents(
    document_id: int,
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Find documents similar to the given document"""
    
    # Verify document belongs to user
    document = db.query(Document).filter(
        Document.id == document_id,
        Document.user_id == current_user.id
    ).first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Get document chunks for similarity search
    chunks = db.query(DocumentChunk).filter(
        DocumentChunk.document_id == document_id
    ).limit(3).all()  # Use first 3 chunks for similarity
    
    similar_docs = []
    
    for chunk in chunks:
        if chunk.embedding:
            try:
                embedding = json.loads(chunk.embedding)
                vector_results = await vector_service.search_similar(
                    embedding,
                    top_k=limit * 2,  # Get more results to filter out same document
                    filter_dict={"user_id": current_user.id}
                )
                
                for result in vector_results:
                    result_chunk = db.query(DocumentChunk).filter(
                        DocumentChunk.id == result['id']
                    ).first()
                    
                    if (result_chunk and 
                        result_chunk.document and 
                        result_chunk.document.id != document_id):
                        
                        # Check if document already added
                        existing = next((d for d in similar_docs if d.document_id == result_chunk.document.id), None)
                        if not existing:
                            similar_docs.append(SearchResult(
                                document_id=result_chunk.document.id,
                                filename=result_chunk.document.original_filename,
                                content_snippet=result_chunk.content[:200] + "..." if len(result_chunk.content) > 200 else result_chunk.content,
                                relevance_score=result['score']
                            ))
            except Exception as e:
                print(f"Error finding similar documents: {e}")
    
    # Sort by relevance and limit
    similar_docs.sort(key=lambda x: x.relevance_score, reverse=True)
    return similar_docs[:limit]

def _extract_snippet(content: str, query: str, snippet_length: int = 200) -> str:
    """Extract a relevant snippet from content around the query"""
    if not content or not query:
        return content[:snippet_length] + "..." if len(content) > snippet_length else content
    
    # Find query position (case insensitive)
    query_lower = query.lower()
    content_lower = content.lower()
    
    pos = content_lower.find(query_lower)
    if pos == -1:
        # Query not found, return beginning
        return content[:snippet_length] + "..." if len(content) > snippet_length else content
    
    # Calculate snippet start position
    start = max(0, pos - snippet_length // 2)
    end = start + snippet_length
    
    snippet = content[start:end]
    
    # Add ellipsis if needed
    if start > 0:
        snippet = "..." + snippet
    if end < len(content):
        snippet = snippet + "..."
    
    return snippet

