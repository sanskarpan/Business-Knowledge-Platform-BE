from datetime import datetime, timedelta
import json
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User, Document, ChatSession, SearchQuery, UserActivity
from app.schemas import UsageAnalytics, DocumentAnalytics
from app.security import get_current_user


router = APIRouter()


@router.get("/usage", response_model=UsageAnalytics)
async def get_usage_analytics(
    days: int = Query(30, ge=1, le=365, description="Number of days to analyze"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get usage analytics for the current user"""

    # Calculate date range
    end_date = datetime.utcnow()
    start_date = end_date - timedelta(days=days)

    # Total counts
    total_documents = db.query(Document).filter(Document.user_id == current_user.id).count()

    total_searches = (
        db.query(SearchQuery)
        .filter(SearchQuery.user_id == current_user.id, SearchQuery.timestamp >= start_date)
        .count()
    )

    total_chat_sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id, ChatSession.created_at >= start_date)
        .count()
    )

    # Recent activities
    recent_activities = (
        db.query(UserActivity)
        .filter(UserActivity.user_id == current_user.id, UserActivity.timestamp >= start_date)
        .order_by(desc(UserActivity.timestamp))
        .limit(20)
        .all()
    )

    activities_list = []
    for activity in recent_activities:
        activities_list.append(
            {
                "id": activity.id,
                "action": activity.action,
                "resource_id": activity.resource_id,
                "timestamp": activity.timestamp.isoformat(),
                "details": json.loads(activity.details) if activity.details else {},
            }
        )

    return UsageAnalytics(
        total_documents=total_documents,
        total_searches=total_searches,
        total_chat_sessions=total_chat_sessions,
        recent_activities=activities_list,
    )


@router.get("/documents", response_model=DocumentAnalytics)
async def get_document_analytics(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get document analytics for the current user"""

    # Total documents
    total_documents = db.query(Document).filter(Document.user_id == current_user.id).count()

    # Documents by file type
    file_type_stats = (
        db.query(Document.file_type, func.count(Document.id).label("count"))
        .filter(Document.user_id == current_user.id)
        .group_by(Document.file_type)
        .all()
    )

    documents_by_type: Dict[str, int] = {}
    for file_type, count in file_type_stats:
        display_type = _simplify_file_type(file_type)
        documents_by_type[display_type] = count

    # Recent uploads (last 10)
    recent_uploads = (
        db.query(Document)
        .filter(Document.user_id == current_user.id)
        .order_by(desc(Document.created_at))
        .limit(10)
        .all()
    )

    recent_uploads_list: List[Dict[str, Any]] = []
    for doc in recent_uploads:
        recent_uploads_list.append(
            {
                "id": doc.id,
                "filename": doc.original_filename,
                "file_type": _simplify_file_type(doc.file_type),
                "file_size": doc.file_size,
                "created_at": doc.created_at.isoformat(),
            }
        )

    return DocumentAnalytics(
        total_documents=total_documents,
        documents_by_type=documents_by_type,
        recent_uploads=recent_uploads_list,
    )


@router.get("/dashboard")
async def get_dashboard_data(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get comprehensive dashboard data"""

    now = datetime.utcnow()
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_ago = today - timedelta(days=7)

    # Activity stats
    activities_today = (
        db.query(UserActivity)
        .filter(UserActivity.user_id == current_user.id, UserActivity.timestamp >= today)
        .count()
    )

    activities_week = (
        db.query(UserActivity)
        .filter(UserActivity.user_id == current_user.id, UserActivity.timestamp >= week_ago)
        .count()
    )

    # Search stats
    searches_today = (
        db.query(SearchQuery)
        .filter(SearchQuery.user_id == current_user.id, SearchQuery.timestamp >= today)
        .count()
    )

    searches_week = (
        db.query(SearchQuery)
        .filter(SearchQuery.user_id == current_user.id, SearchQuery.timestamp >= week_ago)
        .count()
    )

    # Chat stats
    chat_sessions_week = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == current_user.id, ChatSession.created_at >= week_ago)
        .count()
    )

    # Document upload stats
    uploads_week = (
        db.query(Document)
        .filter(Document.user_id == current_user.id, Document.created_at >= week_ago)
        .count()
    )

    # Storage usage
    total_storage = (
        db.query(func.sum(Document.file_size)).filter(Document.user_id == current_user.id).scalar() or 0
    )

    # Most active days (activities per day for last 7 days)
    daily_activity: List[Dict[str, Any]] = []
    for i in range(7):
        day_start = today - timedelta(days=i)
        day_end = day_start + timedelta(days=1)

        day_activities = (
            db.query(UserActivity)
            .filter(
                UserActivity.user_id == current_user.id,
                UserActivity.timestamp >= day_start,
                UserActivity.timestamp < day_end,
            )
            .count()
        )

        daily_activity.append({"date": day_start.strftime("%Y-%m-%d"), "activities": day_activities})

    return {
        "summary": {
            "activities_today": activities_today,
            "activities_week": activities_week,
            "searches_today": searches_today,
            "searches_week": searches_week,
            "chat_sessions_week": chat_sessions_week,
            "uploads_week": uploads_week,
            "total_storage_bytes": total_storage,
            "total_storage_mb": round(total_storage / (1024 * 1024), 2),
        },
        "daily_activity": daily_activity,
        "trends": {
            "activity_trend": "up" if activities_week > activities_today * 7 else "down",
            "search_trend": "up" if searches_week > searches_today * 7 else "down",
        },
    }


@router.get("/performance")
async def get_performance_metrics(
    current_user: User = Depends(get_current_user), db: Session = Depends(get_db)
):
    """Get system performance metrics for the user"""

    # Average search results
    avg_search_results = (
        db.query(func.avg(SearchQuery.results_count))
        .filter(SearchQuery.user_id == current_user.id, SearchQuery.results_count > 0)
        .scalar()
        or 0
    )

    # Most searched terms (from search queries)
    popular_searches = (
        db.query(SearchQuery.query, func.count(SearchQuery.id).label("count"))
        .filter(SearchQuery.user_id == current_user.id)
        .group_by(SearchQuery.query)
        .order_by(desc("count"))
        .limit(10)
        .all()
    )

    popular_searches_list = [
        {"query": query, "count": count} for query, count in popular_searches
    ]

    return {
        "search_performance": {
            "average_results_per_search": round(avg_search_results, 2),
            "popular_searches": popular_searches_list,
        },
        "system_health": {
            "status": "healthy",
            "last_updated": datetime.utcnow().isoformat(),
        },
    }


def _simplify_file_type(mime_type: str) -> str:
    """Convert MIME type to user-friendly format"""
    type_mapping = {
        "application/pdf": "PDF",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "Word",
        "text/plain": "Text",
        "text/markdown": "Markdown",
        "image/jpeg": "Image",
        "image/png": "Image",
        "image/gif": "Image",
    }
    return type_mapping.get(mime_type, "Other")



