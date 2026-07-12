from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from app.models import ActivityLog, Notification, User

def log_activity(
    db: Session, 
    user_id: Optional[int], 
    action: str, 
    details: Optional[Dict[str, Any]] = None
) -> ActivityLog:
    """Log admin, manager, or employee actions to the central audit trail."""
    log = ActivityLog(user_id=user_id, action=action, details=details)
    db.add(log)
    db.commit()
    db.refresh(log)
    return log

def create_notification(
    db: Session, 
    user_id: int, 
    title: str, 
    message: str, 
    type_: str
) -> Notification:
    """Inject a new notification alert into a user's inbox."""
    notification = Notification(
        user_id=user_id, 
        title=title, 
        message=message, 
        type=type_, 
        is_read=False
    )
    db.add(notification)
    db.commit()
    db.refresh(notification)
    return notification
