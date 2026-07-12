from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db import get_db
from app.models import User, UserRole, UserStatus
from app.schemas import UserResponse, UserUpdateRole, UserUpdateStatus
from app.auth import get_current_user, require_role
from app.crud import log_activity

router = APIRouter(prefix="/employees", tags=["Employee Directory"])

# Admin check dependency
admin_dependency = require_role([UserRole.ADMIN])

@router.get("/", response_model=List[UserResponse])
def list_employees(
    db: Session = Depends(get_db),
    # Any authenticated user can view the employee directory
    current_user: User = Depends(get_current_user)
):
    """Retrieve the complete list of employees (Name, Email, Department, Role, Status)."""
    return db.query(User).order_by(User.name).all()


@router.put("/{id}/role", response_model=UserResponse)
def promote_employee_role(
    id: int,
    role_in: UserUpdateRole,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_dependency)
):
    """Admin-only: Promote or modify employee roles (e.g. promoting to Department Head or Asset Manager)."""
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Employee not found"
        )
        
    old_role = user.role
    user.role = role_in.role
    db.commit()
    db.refresh(user)
    
    log_activity(
        db, 
        admin.id, 
        "PROMOTE_EMPLOYEE", 
        {"employee_id": user.id, "old_role": old_role.value, "new_role": user.role.value}
    )
    return user


@router.put("/{id}/status", response_model=UserResponse)
def toggle_employee_status(
    id: int,
    status_in: UserUpdateStatus,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_dependency)
):
    """Admin-only: Toggle employee status between ACTIVE and INACTIVE."""
    user = db.query(User).filter(User.id == id).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Employee not found"
        )
        
    old_status = user.status
    user.status = status_in.status
    db.commit()
    db.refresh(user)
    
    log_activity(
        db, 
        admin.id, 
        "TOGGLE_EMPLOYEE_STATUS", 
        {"employee_id": user.id, "old_status": old_status.value, "new_status": user.status.value}
    )
    return user
