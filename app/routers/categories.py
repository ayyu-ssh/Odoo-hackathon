from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.db import get_db
from app.models import AssetCategory, User, UserRole
from app.schemas import CategoryCreate, CategoryUpdate, CategoryResponse
from app.auth import require_role, get_current_user
from app.crud import log_activity

router = APIRouter(prefix="/categories", tags=["Asset Category Management"])

# Admin check dependency
admin_dependency = require_role([UserRole.ADMIN])

@router.post("/", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(
    cat_in: CategoryCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_dependency)
):
    """Admin-only: Create a new asset category."""
    existing = db.query(AssetCategory).filter(AssetCategory.name == cat_in.name).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Category name already exists"
        )
        
    cat = AssetCategory(
        name=cat_in.name,
        fields_schema=cat_in.fields_schema
    )
    db.add(cat)
    db.commit()
    db.refresh(cat)
    
    log_activity(db, admin.id, "CREATE_CATEGORY", {"id": cat.id, "name": cat.name})
    return cat


@router.put("/{id}", response_model=CategoryResponse)
def update_category(
    id: int,
    cat_in: CategoryUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_dependency)
):
    """Admin-only: Update category schemas."""
    cat = db.query(AssetCategory).filter(AssetCategory.id == id).first()
    if not cat:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Category not found"
        )
        
    if cat_in.name is not None:
        other = db.query(AssetCategory).filter(AssetCategory.name == cat_in.name, AssetCategory.id != id).first()
        if other:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Category name already exists"
            )
        cat.name = cat_in.name
        
    if cat_in.fields_schema is not None:
        cat.fields_schema = cat_in.fields_schema
        
    db.commit()
    db.refresh(cat)
    
    log_activity(db, admin.id, "UPDATE_CATEGORY", {"id": cat.id, "name": cat.name})
    return cat


@router.get("/", response_model=List[CategoryResponse])
def list_categories(
    db: Session = Depends(get_db),
    # Accessible to all users for registration drop-downs
    current_user: User = Depends(get_current_user)
):
    """List all asset categories."""
    return db.query(AssetCategory).order_by(AssetCategory.name).all()
