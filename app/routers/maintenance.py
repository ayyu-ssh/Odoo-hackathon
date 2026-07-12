from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db import get_db
from app.models import (
    Asset,
    MaintenanceRequest,
    User,
    UserRole,
    AssetStatus,
    MaintenanceStatus,
    MaintenancePriority
)
from app.schemas import MaintenanceCreate, MaintenanceResponse, MaintenanceUpdate
from app.auth import get_current_user, require_role
from app.crud import log_activity, create_notification

router = APIRouter(prefix="/maintenance", tags=["Maintenance Management"])

# Asset Manager / Admin checks
manager_dependency = require_role([UserRole.ADMIN, UserRole.ASSET_MANAGER])

@router.post("/", response_model=MaintenanceResponse, status_code=status.HTTP_201_CREATED)
def raise_maintenance_request(
    req_in: MaintenanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Raise a maintenance ticket for an asset. Available to all employees."""
    asset = db.query(Asset).filter(Asset.id == req_in.asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Optional security check: employees can raise for their allocated assets, managers can raise for anything
    # Let's keep it open to allow easy reports from holders as requested in user workflow.
    
    req = MaintenanceRequest(
        asset_id=req_in.asset_id,
        raised_by_id=current_user.id,
        description=req_in.description,
        priority=req_in.priority,
        photo_url=req_in.photo_url,
        status=MaintenanceStatus.PENDING
    )
    db.add(req)
    db.commit()
    db.refresh(req)

    log_activity(db, current_user.id, "RAISE_MAINTENANCE", {"request_id": req.id})
    return req


@router.post("/{id}/approve", response_model=MaintenanceResponse)
def approve_maintenance_request(
    id: int,
    approve: bool = True,
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """
    Asset Manager: Approve or reject a maintenance ticket.
    On approval: Asset status automatically flips to UNDER_MAINTENANCE.
    """
    req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Maintenance ticket not found")

    if req.status != MaintenanceStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Ticket is already approved/rejected"
        )

    if approve:
        req.status = MaintenanceStatus.APPROVED
        req.approved_by_id = manager.id
        # Update asset status
        asset = db.query(Asset).filter(Asset.id == req.asset_id).first()
        if asset:
            asset.status = AssetStatus.UNDER_MAINTENANCE
            
        create_notification(
            db, 
            req.raised_by_id, 
            "Maintenance Approved", 
            f"Your maintenance request for asset ID {req.asset_id} has been approved.",
            "MaintenanceApproved"
        )
    else:
        req.status = MaintenanceStatus.REJECTED
        req.approved_by_id = manager.id
        create_notification(
            db, 
            req.raised_by_id, 
            "Maintenance Rejected", 
            f"Your maintenance request for asset ID {req.asset_id} has been rejected.", 
            "MaintenanceRejected"
        )

    db.commit()
    db.refresh(req)

    log_activity(
        db, 
        manager.id, 
        "APPROVE_MAINTENANCE", 
        {"request_id": id, "approved": approve}
    )
    return req


@router.post("/{id}/assign", response_model=MaintenanceResponse)
def assign_technician(
    id: int,
    technician_id: int,
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """Asset Manager: Assign a technician to an approved ticket."""
    req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Maintenance ticket not found")

    if req.status not in [MaintenanceStatus.APPROVED, MaintenanceStatus.TECHNICIAN_ASSIGNED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Ticket must be approved before assigning a technician"
        )

    # Verify technician employee exists
    tech = db.query(User).filter(User.id == technician_id).first()
    if not tech:
        raise HTTPException(status_code=400, detail="Technician not found in directory")

    req.technician_id = technician_id
    req.status = MaintenanceStatus.TECHNICIAN_ASSIGNED

    db.commit()
    db.refresh(req)

    create_notification(
        db, 
        technician_id, 
        "Maintenance Ticket Assigned", 
        f"You have been assigned to repair asset ID {req.asset_id}.", 
        "AssetAssigned"
    )
    
    log_activity(
        db, 
        manager.id, 
        "ASSIGN_TECHNICIAN", 
        {"request_id": id, "technician_id": technician_id}
    )
    return req


@router.post("/{id}/start", response_model=MaintenanceResponse)
def start_maintenance(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Mark ticket as IN_PROGRESS. Available to assigned technician or managers."""
    req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Maintenance ticket not found")

    # Check permission
    if (
        req.technician_id != current_user.id and 
        current_user.role not in [UserRole.ADMIN, UserRole.ASSET_MANAGER]
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only the assigned technician or managers can start repair work"
        )

    if req.status != MaintenanceStatus.TECHNICIAN_ASSIGNED:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Ticket status must be TECHNICIAN_ASSIGNED to start"
        )

    req.status = MaintenanceStatus.IN_PROGRESS
    db.commit()
    db.refresh(req)

    log_activity(db, current_user.id, "START_MAINTENANCE", {"request_id": id})
    return req


@router.post("/{id}/resolve", response_model=MaintenanceResponse)
def resolve_maintenance(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Mark maintenance as RESOLVED.
    On resolution: Asset status automatically reverts back to AVAILABLE.
    Available to assigned technician or managers.
    """
    req = db.query(MaintenanceRequest).filter(MaintenanceRequest.id == id).first()
    if not req:
        raise HTTPException(status_code=404, detail="Maintenance ticket not found")

    # Check permission
    if (
        req.technician_id != current_user.id and 
        current_user.role not in [UserRole.ADMIN, UserRole.ASSET_MANAGER]
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Only the assigned technician or managers can resolve repair work"
        )

    if req.status not in [MaintenanceStatus.IN_PROGRESS, MaintenanceStatus.TECHNICIAN_ASSIGNED]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Work must be active/in-progress to resolve"
        )

    req.status = MaintenanceStatus.RESOLVED
    
    # Revert asset status back to AVAILABLE
    asset = db.query(Asset).filter(Asset.id == req.asset_id).first()
    if asset:
        asset.status = AssetStatus.AVAILABLE
        
    db.commit()
    db.refresh(req)

    create_notification(
        db, 
        req.raised_by_id, 
        "Maintenance Resolved", 
        f"Repair work for asset ID {req.asset_id} is now complete.", 
        "AssetAssigned"
    )
    
    log_activity(db, current_user.id, "RESOLVE_MAINTENANCE", {"request_id": id})
    return req


@router.get("/", response_model=List[MaintenanceResponse])
def list_maintenance_requests(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve list of maintenance tickets. Scoped to role (employees see their own, techs see assigned, managers see all)."""
    if current_user.role in [UserRole.ADMIN, UserRole.ASSET_MANAGER]:
        return db.query(MaintenanceRequest).order_by(MaintenanceRequest.created_at.desc()).all()
    elif req_tech := db.query(MaintenanceRequest).filter(MaintenanceRequest.technician_id == current_user.id).all():
        return req_tech
    else:
        return db.query(MaintenanceRequest).filter(MaintenanceRequest.raised_by_id == current_user.id).all()
