from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db import get_db
from app.models import Department, User, UserRole, UserStatus
from app.schemas import DepartmentCreate, DepartmentUpdate, DepartmentResponse
from app.auth import require_role, get_current_user
from app.crud import log_activity

router = APIRouter(prefix="/departments", tags=["Department Management"])

# Setup permission dependency
admin_dependency = require_role([UserRole.ADMIN])

@router.post("/", response_model=DepartmentResponse, status_code=status.HTTP_201_CREATED)
def create_department(
    dept_in: DepartmentCreate, 
    db: Session = Depends(get_db),
    admin: User = Depends(admin_dependency)
):
    """Admin-only: Create a new department."""
    # Check if department already exists
    existing = db.query(Department).filter(Department.name == dept_in.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Department name already exists"
        )
    
    # Check parent department if provided
    if dept_in.parent_id:
        parent = db.query(Department).filter(Department.id == dept_in.parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Parent department not found"
            )
            
    # Check head employee if provided
    if dept_in.head_id:
        head = db.query(User).filter(User.id == dept_in.head_id).first()
        if not head:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Assigned Department Head not found in employee directory"
            )
            
    dept = Department(
        name=dept_in.name,
        head_id=dept_in.head_id,
        parent_id=dept_in.parent_id,
        status=dept_in.status
    )
    db.add(dept)
    db.commit()
    db.refresh(dept)
    
    # If a department head is assigned, update user's role if needed
    # Note: Promoting happens in Directory Tab C, but setting head_id will align references
    log_activity(db, admin.id, "CREATE_DEPARTMENT", {"id": dept.id, "name": dept.name})
    return dept


@router.put("/{id}", response_model=DepartmentResponse)
def update_department(
    id: int, 
    dept_in: DepartmentUpdate, 
    db: Session = Depends(get_db),
    admin: User = Depends(admin_dependency)
):
    """Admin-only: Update department details, assign head, parent department, or set status."""
    dept = db.query(Department).filter(Department.id == id).first()
    if not dept:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Department not found"
        )
        
    if dept_in.name is not None:
        # Check uniqueness
        other = db.query(Department).filter(Department.name == dept_in.name, Department.id != id).first()
        if other:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Department name already exists"
            )
        dept.name = dept_in.name
        
    if dept_in.parent_id is not None:
        if dept_in.parent_id == id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="A department cannot be its own parent"
            )
        parent = db.query(Department).filter(Department.id == dept_in.parent_id).first()
        if not parent:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Parent department not found"
            )
        dept.parent_id = dept_in.parent_id
        
    if dept_in.head_id is not None:
        head = db.query(User).filter(User.id == dept_in.head_id).first()
        if not head:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Assigned Department Head not found in employee directory"
            )
        dept.head_id = dept_in.head_id
        
    if dept_in.status is not None:
        dept.status = dept_in.status
        # Optionally recursively cascade active/inactive if desired
        
    db.commit()
    db.refresh(dept)
    
    log_activity(db, admin.id, "UPDATE_DEPARTMENT", {"id": dept.id, "name": dept.name})
    return dept


@router.get("/", response_model=List[DepartmentResponse])
def list_departments(
    db: Session = Depends(get_db),
    # Any active user can list departments to find parent/hierarchy contexts
    current_user: User = Depends(get_current_user)
):
    """List all departments."""
    return db.query(Department).order_by(Department.name).all()
