import re
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db import get_db
from app.models import Asset, AssetCategory, AssetAllocation, Department, MaintenanceRequest, User, UserRole, AssetStatus
from app.schemas import AssetCreate, AssetUpdate, AssetResponse
from app.auth import get_current_user, require_role
from app.crud import log_activity

router = APIRouter(prefix="/assets", tags=["Asset Directory"])

# Role guard for registering/modifying assets
manager_dependency = require_role([UserRole.ADMIN, UserRole.ASSET_MANAGER])

def generate_next_asset_tag(db: Session) -> str:
    """Helper to retrieve the maximum asset tag and increment it safely to prevent collisions."""
    # Find highest tag matching pattern AF-XXXX
    results = db.query(Asset.asset_tag).all()
    max_num = 0
    for res in results:
        match = re.match(r"^AF-(\d+)$", res[0])
        if match:
            num = int(match.group(1))
            if num > max_num:
                max_num = num
    return f"AF-{max_num + 1:04d}"


@router.post("/", response_model=AssetResponse, status_code=status.HTTP_201_CREATED)
def register_asset(
    asset_in: AssetCreate,
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """Asset Manager / Admin: Register a new physical asset with custom fields validation."""
    # Validate category exists
    category = db.query(AssetCategory).filter(AssetCategory.id == asset_in.category_id).first()
    if not category:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Asset Category not found"
        )
        
    # Validate unique serial number if provided
    if asset_in.serial_number:
        dup = db.query(Asset).filter(Asset.serial_number == asset_in.serial_number).first()
        if dup:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail="Asset with this serial number already registered"
            )
            
    # Validate category-specific fields against schema if defined
    if category.fields_schema and asset_in.category_attributes:
        for field, f_type in category.fields_schema.items():
            # Check fields
            if field in asset_in.category_attributes:
                val = asset_in.category_attributes[field]
                # Basic type checking
                if f_type == "int" and not isinstance(val, int):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail=f"Field '{field}' must be an integer (specified by category schema)"
                    )
                elif f_type == "str" and not isinstance(val, str):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail=f"Field '{field}' must be a string (specified by category schema)"
                    )
                elif f_type == "float" and not isinstance(val, (int, float)):
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST, 
                        detail=f"Field '{field}' must be a float (specified by category schema)"
                    )
                    
    # Generate tag
    tag = generate_next_asset_tag(db)
    
    asset = Asset(
        name=asset_in.name,
        category_id=asset_in.category_id,
        asset_tag=tag,
        serial_number=asset_in.serial_number,
        acquisition_date=asset_in.acquisition_date,
        acquisition_cost=asset_in.acquisition_cost,
        condition=asset_in.condition,
        location=asset_in.location,
        photo_url=asset_in.photo_url,
        documents_url=asset_in.documents_url,
        is_shared_bookable=asset_in.is_shared_bookable,
        status=AssetStatus.AVAILABLE,  # Default to available
        category_attributes=asset_in.category_attributes
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    
    log_activity(db, manager.id, "REGISTER_ASSET", {"id": asset.id, "asset_tag": asset.asset_tag})
    return asset


@router.get("/", response_model=List[AssetResponse])
def search_assets(
    tag: Optional[str] = Query(None, alias="asset_tag"),
    serial_number: Optional[str] = None,
    category_id: Optional[int] = None,
    status: Optional[AssetStatus] = None,
    location: Optional[str] = None,
    is_shared_bookable: Optional[bool] = None,
    search: Optional[str] = Query(None, description="General search by name or condition"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Search/filter assets across all dimensions."""
    query = db.query(Asset)
    
    if tag:
        query = query.filter(Asset.asset_tag.ilike(f"%{tag}%"))
    if serial_number:
        query = query.filter(Asset.serial_number.ilike(f"%{serial_number}%"))
    if category_id:
        query = query.filter(Asset.category_id == category_id)
    if status:
        query = query.filter(Asset.status == status)
    if location:
        query = query.filter(Asset.location.ilike(f"%{location}%"))
    if is_shared_bookable is not None:
        query = query.filter(Asset.is_shared_bookable == is_shared_bookable)
    if search:
        query = query.filter(
            Asset.name.ilike(f"%{search}%") | 
            Asset.condition.ilike(f"%{search}%")
        )
        
    return query.order_by(Asset.asset_tag).all()


@router.get("/{id}")
def get_asset_details(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve full asset specs + historical allocation ledger + maintenance logs."""
    asset = db.query(Asset).filter(Asset.id == id).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Asset not found"
        )
        
    # Fetch allocation history
    allocations = (
        db.query(AssetAllocation)
        .filter(AssetAllocation.asset_id == id)
        .order_by(AssetAllocation.created_at.desc())
        .all()
    )
    
    # Fetch maintenance history
    maintenance = (
        db.query(MaintenanceRequest)
        .filter(MaintenanceRequest.asset_id == id)
        .order_by(MaintenanceRequest.created_at.desc())
        .all()
    )
    
    # Map logs into serializable structure
    allocation_history = []
    for alloc in allocations:
        assignee = ""
        if alloc.allocated_to_user_id:
            user = db.query(User).filter(User.id == alloc.allocated_to_user_id).first()
            if user:
                assignee = f"Employee: {user.name} ({user.email})"
        elif alloc.allocated_to_department_id:
            dept = db.query(Department).filter(Department.id == alloc.allocated_to_department_id).first()
            if dept:
                assignee = f"Department: {dept.name}"
                
        allocation_history.append({
            "id": alloc.id,
            "assigned_to": assignee,
            "allocated_at": alloc.created_at,
            "expected_return": alloc.expected_return_date,
            "returned_at": alloc.returned_at,
            "status": alloc.status,
            "condition_on_return": alloc.condition_on_return
        })
        
    maintenance_history = [{
        "id": req.id,
        "description": req.description,
        "priority": req.priority.value,
        "status": req.status.value,
        "created_at": req.created_at,
        "updated_at": req.updated_at
    } for req in maintenance]
    
    return {
        "asset": asset,
        "history": {
            "allocations": allocation_history,
            "maintenance": maintenance_history
        }
    }


@router.put("/{id}", response_model=AssetResponse)
def update_asset(
    id: int,
    asset_in: AssetUpdate,
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """Asset Manager / Admin: Update an existing asset."""
    asset = db.query(Asset).filter(Asset.id == id).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Asset not found"
        )
        
    # Apply changes
    update_data = asset_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(asset, field, value)
        
    db.commit()
    db.refresh(asset)
    
    log_activity(db, manager.id, "UPDATE_ASSET", {"id": asset.id, "asset_tag": asset.asset_tag})
    return asset
