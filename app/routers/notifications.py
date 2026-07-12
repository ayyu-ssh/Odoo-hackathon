from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db import get_db
from app.models import Notification, ActivityLog, User, UserRole
from app.schemas import NotificationResponse, ActivityLogResponse
from app.auth import get_current_user, require_role

router = APIRouter(tags=["Notifications & Logs"])

# Access controls
admin_dependency = require_role([UserRole.ADMIN])

@router.get("/notifications", response_model=List[NotificationResponse])
def get_user_notifications(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve all notifications (overdue alerts, approvals, bookings) scoped to the current user."""
    return (
        db.query(Notification)
        .filter(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc())
        .all()
    )


@router.post("/notifications/{id}/read", response_model=NotificationResponse)
def mark_notification_read(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark a specific notification as read."""
    notification = db.query(Notification).filter(Notification.id == id).first()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")
        
    # Security: user can only mark their own notifications
    if notification.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authorized to access this notification"
        )
        
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@router.get("/logs", response_model=List[ActivityLogResponse])
def get_activity_logs(
    db: Session = Depends(get_db),
    admin: User = Depends(admin_dependency)
):
    """Admin-only: Retrieve all system activity logs (audit trails of actions, who did what, when)."""
    return (
        db.query(ActivityLog)
        .order_by(ActivityLog.created_at.desc())
        .limit(200)
        .all()
    )
