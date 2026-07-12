from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db import get_db
from app.models import (
    Asset,
    AssetAllocation,
    TransferRequest,
    User,
    UserRole,
    AssetStatus,
    Department,
    TransferStatus
)
from app.schemas import (
    AllocationCreate,
    AllocationResponse,
    TransferRequestCreate,
    TransferRequestResponse,
    AssetReturnRequest
)
from app.auth import get_current_user, require_role
from app.crud import log_activity, create_notification

router = APIRouter(prefix="/allocations", tags=["Asset Allocation & Transfers"])

@router.post("/allocate", response_model=AllocationResponse)
def allocate_asset(
    alloc_in: AllocationCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Allocate an asset to an employee or department.
    Conflict rule: Blocks double-allocation. If already taken, returns 409 and who holds it.
    """
    # Enforce role: Asset Managers or Admins only
    if current_user.role not in [UserRole.ADMIN, UserRole.ASSET_MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Asset Managers or Admins can allocate assets."
        )

    asset = db.query(Asset).filter(Asset.id == alloc_in.asset_id).first()
    if not asset:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Asset not found"
        )
        
    # Check if asset is not available (Conflict check)
    if asset.status != AssetStatus.AVAILABLE:
        # Find who holds it right now
        active_alloc = (
            db.query(AssetAllocation)
            .filter(AssetAllocation.asset_id == asset.id, AssetAllocation.status == "ACTIVE")
            .first()
        )
        holder_info = "Unknown"
        if active_alloc:
            if active_alloc.allocated_to_user_id:
                user = db.query(User).filter(User.id == active_alloc.allocated_to_user_id).first()
                if user:
                    holder_info = f"{user.name} ({user.email})"
            elif active_alloc.allocated_to_department_id:
                dept = db.query(Department).filter(Department.id == active_alloc.allocated_to_department_id).first()
                if dept:
                    holder_info = f"Department: {dept.name}"
                    
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Asset already allocated. Currently held by {holder_info}.",
                "currently_held_by": holder_info,
                "asset_id": asset.id,
                "asset_tag": asset.asset_tag,
                "transfer_available": True
            }
        )

    # Validate target user or department
    if alloc_in.allocated_to_user_id:
        target_user = db.query(User).filter(User.id == alloc_in.allocated_to_user_id).first()
        if not target_user:
            raise HTTPException(status_code=400, detail="Target employee not found")
    elif alloc_in.allocated_to_department_id:
        target_dept = db.query(Department).filter(Department.id == alloc_in.allocated_to_department_id).first()
        if not target_dept:
            raise HTTPException(status_code=400, detail="Target department not found")
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Must allocate to either an employee or a department"
        )

    # Create allocation record
    new_alloc = AssetAllocation(
        asset_id=asset.id,
        allocated_to_user_id=alloc_in.allocated_to_user_id,
        allocated_to_department_id=alloc_in.allocated_to_department_id,
        expected_return_date=alloc_in.expected_return_date,
        status="ACTIVE"
    )
    # Update asset state
    asset.status = AssetStatus.ALLOCATED
    
    db.add(new_alloc)
    db.commit()
    db.refresh(new_alloc)

    # Send Notification
    msg = f"Asset {asset.name} ({asset.asset_tag}) has been allocated to you."
    if alloc_in.allocated_to_user_id:
        create_notification(db, alloc_in.allocated_to_user_id, "Asset Allocated", msg, "AssetAssigned")
        
    log_activity(db, current_user.id, "ALLOCATE_ASSET", {"asset_id": asset.id, "allocation_id": new_alloc.id})
    return new_alloc


@router.post("/transfer/request", response_model=TransferRequestResponse)
def request_transfer(
    req_in: TransferRequestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Raise a transfer request for an asset that is currently allocated."""
    asset = db.query(Asset).filter(Asset.id == req_in.asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    # Get current active allocation
    active_alloc = (
        db.query(AssetAllocation)
        .filter(AssetAllocation.asset_id == asset.id, AssetAllocation.status == "ACTIVE")
        .first()
    )
    if not active_alloc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Asset is not currently allocated. You can allocate it directly."
        )

    # Validate target
    if not req_in.to_user_id and not req_in.to_department_id:
        raise HTTPException(status_code=400, detail="Must specify a target employee or department")

    transfer_req = TransferRequest(
        asset_id=asset.id,
        from_user_id=active_alloc.allocated_to_user_id,
        from_department_id=active_alloc.allocated_to_department_id,
        to_user_id=req_in.to_user_id,
        to_department_id=req_in.to_department_id,
        requested_by_id=current_user.id,
        status=TransferStatus.PENDING
    )
    db.add(transfer_req)
    db.commit()
    db.refresh(transfer_req)

    # Notify managers & potential holders
    log_activity(db, current_user.id, "REQUEST_TRANSFER", {"transfer_id": transfer_req.id})
    return transfer_req


@router.post("/transfer/{id}/approve", response_model=TransferRequestResponse)
def approve_transfer(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Approve transfer request.
    Authorized: Asset Manager, Admin, or Department Head (if transfer is within their department).
    """
    transfer_req = db.query(TransferRequest).filter(TransferRequest.id == id).first()
    if not transfer_req:
        raise HTTPException(status_code=404, detail="Transfer request not found")
        
    if transfer_req.status != TransferStatus.PENDING:
        raise HTTPException(status_code=400, detail="Transfer request is already resolved")

    # Authorize:
    is_authorized = False
    if current_user.role in [UserRole.ADMIN, UserRole.ASSET_MANAGER]:
        is_authorized = True
    elif current_user.role == UserRole.DEPARTMENT_HEAD:
        # Check if the head manages either the "from" or "to" department
        managed_dept_ids = [d.id for d in current_user.headed_departments]
        
        # Check if target user belongs to department
        target_user_dept_id = None
        if transfer_req.to_user_id:
            tu = db.query(User).filter(User.id == transfer_req.to_user_id).first()
            if tu:
                target_user_dept_id = tu.department_id

        # Check if source user belongs to department
        source_user_dept_id = None
        if transfer_req.from_user_id:
            su = db.query(User).filter(User.id == transfer_req.from_user_id).first()
            if su:
                source_user_dept_id = su.department_id

        if (
            transfer_req.from_department_id in managed_dept_ids or
            transfer_req.to_department_id in managed_dept_ids or
            target_user_dept_id in managed_dept_ids or
            source_user_dept_id in managed_dept_ids
        ):
            is_authorized = True

    if not is_authorized:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to approve this transfer request"
        )

    # Perform transfer:
    # 1. Terminate active allocation
    active_alloc = (
        db.query(AssetAllocation)
        .filter(AssetAllocation.asset_id == transfer_req.asset_id, AssetAllocation.status == "ACTIVE")
        .first()
    )
    if active_alloc:
        active_alloc.status = "RETURNED"
        active_alloc.returned_at = datetime.utcnow()
        active_alloc.condition_on_return = "Transferred directly"
        active_alloc.return_approved_by_id = current_user.id

    # 2. Create new allocation
    new_alloc = AssetAllocation(
        asset_id=transfer_req.asset_id,
        allocated_to_user_id=transfer_req.to_user_id,
        allocated_to_department_id=transfer_req.to_department_id,
        expected_return_date=active_alloc.expected_return_date if active_alloc else None,
        status="ACTIVE"
    )
    db.add(new_alloc)

    # 3. Update transfer request status
    transfer_req.status = TransferStatus.APPROVED
    transfer_req.approved_by_id = current_user.id

    db.commit()
    db.refresh(transfer_req)

    # Notify new holder
    asset = db.query(Asset).filter(Asset.id == transfer_req.asset_id).first()
    if transfer_req.to_user_id and asset:
        create_notification(
            db, 
            transfer_req.to_user_id, 
            "Asset Transferred", 
            f"Asset {asset.name} ({asset.asset_tag}) has been transferred to you.", 
            "TransferApproved"
        )
        
    log_activity(db, current_user.id, "APPROVE_TRANSFER", {"transfer_id": id})
    return transfer_req


@router.post("/return/{asset_id}", response_model=AllocationResponse)
def return_asset(
    asset_id: int,
    return_in: AssetReturnRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Return allocated asset.
    Authorized: Asset Manager or Admin (approves return and logs condition notes).
    """
    if current_user.role not in [UserRole.ADMIN, UserRole.ASSET_MANAGER]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only Asset Managers or Admins can approve asset returns."
        )

    asset = db.query(Asset).filter(Asset.id == asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    active_alloc = (
        db.query(AssetAllocation)
        .filter(AssetAllocation.asset_id == asset_id, AssetAllocation.status == "ACTIVE")
        .first()
    )
    if not active_alloc:
        raise HTTPException(status_code=400, detail="No active allocation found for this asset")

    # Revert asset status
    asset.status = AssetStatus.AVAILABLE
    asset.condition = return_in.condition_on_return  # Update asset condition with current check-in notes

    # Close allocation record
    active_alloc.status = "RETURNED"
    active_alloc.returned_at = datetime.utcnow()
    active_alloc.condition_on_return = return_in.condition_on_return
    active_alloc.return_approved_by_id = current_user.id

    db.commit()
    db.refresh(active_alloc)

    log_activity(db, current_user.id, "RETURN_ASSET", {"asset_id": asset_id, "allocation_id": active_alloc.id})
    return active_alloc


@router.get("/overdue", response_model=List[AllocationResponse])
def get_overdue_allocations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch all active allocations whose expected return date is in the past."""
    today = datetime.utcnow().date()
    query = db.query(AssetAllocation).filter(
        AssetAllocation.status == "ACTIVE",
        AssetAllocation.expected_return_date < today
    )

    # Apply scopes
    if current_user.role == UserRole.EMPLOYEE:
        query = query.filter(AssetAllocation.allocated_to_user_id == current_user.id)
    elif current_user.role == UserRole.DEPARTMENT_HEAD:
        # Check if allocated to head's department or employee in head's department
        managed_dept_ids = [d.id for d in current_user.headed_departments]
        
        # We can join on User to check user department
        query = query.outerjoin(User, AssetAllocation.allocated_to_user_id == User.id).filter(
            (AssetAllocation.allocated_to_department_id.in_(managed_dept_ids)) |
            (User.department_id.in_(managed_dept_ids))
        )

    return query.order_by(AssetAllocation.expected_return_date).all()
