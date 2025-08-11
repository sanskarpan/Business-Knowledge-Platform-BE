import json
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
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
    
    if search_type in ["text", "hybrid"]:
        # Text-based search
        text_results = db.query(Document).filter(
            and_(
                Document.user_id == current_user.id,
                or_(
                    Document.original_filename.contains(q),
                    Document.content.contains(q)
                )
            )
        ).limit(limit).all()
        
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
                    chunk_id = result['id']
                    chunk = db.query(DocumentChunk).filter(
                        DocumentChunk.id == chunk_id
                    ).first()
                    
                    if chunk and chunk.document:
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

# File: app/routers/analytics.py
import json
from datetime import datetime, timedelta
from typing import List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from app.database import get_db
from app.models import User, Document, ChatSession, SearchQuery, UserActivity
from app.schemas import UsageAnalytics, DocumentAnalytics
from app.security import get_current_user

router = APIRouter()

@router.get("/usage", response_model=UsageAnalytics)
async def get_usage_analytics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get usage analytics for the current user"""
    
    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)
    
    # Total counts
    total_documents = db.query(Document).filter(
        Document.user_id == current_user.id
    ).count()
    
    total_searches = db.query(SearchQuery).filter(
        SearchQuery.user_id == current_user.id,
        SearchQuery.timestamp >= start_date
    ).count()
    
    total_chat_sessions = db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id,
        ChatSession.created_at >= start_date
    ).count()
    
    # Recent activities
    recent_activities = db.query(UserActivity).filter(
        UserActivity.user_id == current_user.id,
        UserActivity.timestamp >= start_date
    ).order_by(desc(UserActivity.timestamp)).limit(20).all()
    
    activities_list = []
    for activity in recent_activities:
        activities_list.append({
            "id": activity.id,
            "action": activity.action,
            "resource_id": activity.resource_id,
            "timestamp": activity.timestamp.isoformat(),
            "details": json.loads(activity.details) if activity.details else {}
        })
    
    return UsageAnalytics(
        total_documents=total_documents,
        total_searches=total_searches,
        total_chat_sessions=total_chat_sessions,
        recent_activities=activities_list
    )

@router.get("/documents", response_model=DocumentAnalytics)
async def get_document_analytics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get document analytics for the current user"""
    
    # Total documents
    total_documents = db.query(Document).filter(
        Document.user_id == current_user.id
    ).count()
    
    # Documents by file type
    file_type_stats = db.query(
        Document.file_type,
        func.count(Document.id).label('count')
    ).filter(
        Document.user_id == current_user.id
    ).group_by(Document.file_type).all()
    
    documents_by_type = {}
    for file_type, count in file_type_stats:
        # Simplify MIME types for display
        display_type = _simplify_file_type(file_type)
        documents_by_type[display_type] = count
    
    # Recent uploads (last 10)
    recent_uploads = db.query(Document).filter(
        Document.user_id == current_user.id
    ).order_by(desc(Document.created_at)).limit(10).all()
    
    recent_uploads_list = []
    for doc in recent_uploads:
        recent_uploads_list.append({
            "id": doc.id,
            "filename": doc.original_filename,
            "file_type": _simplify_file_type(doc.file_type),
            "file_size": doc.file_size,
            "created_at": doc.created_at.isoformat()
        })
    
    return DocumentAnalytics(
        total_documents=total_documents,
        documents_by_type=documents_by_type,
        recent_uploads=recent_uploads_list
    )

@router.get("/dashboard")
async def get_dashboard_data(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get comprehensive dashboard data"""
    
    # Time periods
    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)
    month_ago = today - timedelta(days=30)
    
    # Activity stats
    activities_today = db.query(UserActivity).filter(
        UserActivity.user_id == current_user.id,
        UserActivity.timestamp >= today
    ).count()
    
    activities_week = db.query(UserActivity).filter(
        UserActivity.user_id == current_user.id,
        UserActivity.timestamp >= week_ago
    ).count()
    
    # Search stats
    searches_today = db.query(SearchQuery).filter(
        SearchQuery.user_id == current_user.id,
        SearchQuery.timestamp >= today
    ).count()
    
    searches_week = db.query(SearchQuery).filter(
        SearchQuery.user_id == current_user.id,
        SearchQuery.timestamp >= week_ago
    ).count()
    
    # Chat stats
    chat_sessions_week = db.query(ChatSession).filter(
        ChatSession.user_id == current_user.id,
        ChatSession.created_at >= week_ago
    ).count()
    
    # Document upload stats
    uploads_week = db.query(Document).filter(
        Document.user_id == current_user.id,
        Document.created_at >= week_ago
    ).count()
    
    # Storage usage
    total_storage = db.query(func.sum(Document.file_size)).filter(
        Document.user_id == current_user.id
    ).scalar() or 0
    
    # Most active days (activities per day for last 7 days)
    daily_activity = []
    for i in range(7):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)
        
        day_activities = db.query(UserActivity).filter(
            UserActivity.user_id == current_user.id,
            UserActivity.timestamp >= day_start,
            UserActivity.timestamp < day_end
        ).count()
        
        daily_activity.append({
            "date": day_start.strftime("%Y-%m-%d"),
            "activities": day_activities
        })
    
    return {
        "summary": {
            "activities_today": activities_today,
            "activities_week": activities_week,
            "searches_today": searches_today,
            "searches_week": searches_week,
            "chat_sessions_week": chat_sessions_week,
            "uploads_week": uploads_week,
            "total_storage_bytes": total_storage,
            "total_storage_mb": round(total_storage / (1024 * 1024), 2)
        },
        "daily_activity": daily_activity,
        "trends": {
            "activity_trend": "up" if activities_week > activities_today * 7 else "down",
            "search_trend": "up" if searches_week > searches_today * 7 else "down"
        }
    }

@router.get("/performance")
async def get_performance_metrics(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """Get system performance metrics for the user"""
    
    # Average search results
    avg_search_results = db.query(func.avg(SearchQuery.results_count)).filter(
        SearchQuery.user_id == current_user.id,
        SearchQuery.results_count > 0
    ).scalar() or 0
    
    # Most searched terms (from search queries)
    popular_searches = db.query(
        SearchQuery.query,
        func.count(SearchQuery.id).label('count')
    ).filter(
        SearchQuery.user_id == current_user.id
    ).group_by(SearchQuery.query).order_by(
        desc('count')
    ).limit(10).all()
    
    popular_searches_list = [
        {"query": query, "count": count} 
        for query, count in popular_searches
    ]
    
    # Document engagement (documents referenced in chats)
    # This would require more complex queries to track document usage in chat context
    
    return {
        "search_performance": {
            "average_results_per_search": round(avg_search_results, 2),
            "popular_searches": popular_searches_list
        },
        "system_health": {
            "status": "healthy",
            "last_updated": datetime.utcnow().isoformat()
        }
    }

def _simplify_file_type(mime_type: str) -> str:
    """Convert MIME type to user-friendly format"""
    type_mapping = {
        'application/pdf': 'PDF',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document': 'Word',
        'text/plain': 'Text',
        'text/markdown': 'Markdown',
        'image/jpeg': 'Image',
        'image/png': 'Image',
        'image/gif': 'Image'
    }
    return type_mapping.get(mime_type, 'Other')

