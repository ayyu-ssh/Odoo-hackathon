from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db import get_db
from app.models import (
    AuditCycle,
    AuditRecord,
    Asset,
    User,
    UserRole,
    AssetStatus,
    AuditCycleStatus,
    AuditRecordStatus,
    audit_cycle_auditors
)
from app.schemas import (
    AuditCycleCreate,
    AuditCycleResponse,
    AuditRecordCreate,
    AuditRecordResponse
)
from app.auth import get_current_user, require_role
from app.crud import log_activity, create_notification

router = APIRouter(prefix="/audits", tags=["Asset Verification & Audits"])

# Access guards
admin_dependency = require_role([UserRole.ADMIN])
manager_or_admin = require_role([UserRole.ADMIN, UserRole.ASSET_MANAGER])

@router.post("/cycle", response_model=AuditCycleResponse, status_code=status.HTTP_201_CREATED)
def create_audit_cycle(
    cycle_in: AuditCycleCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_dependency)
):
    """Admin-only: Create an Audit Cycle and assign auditors."""
    # Validate auditor list
    auditors = db.query(User).filter(User.id.in_(cycle_in.auditor_ids)).all()
    if len(auditors) != len(cycle_in.auditor_ids):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Some auditor IDs are invalid"
        )
        
    cycle = AuditCycle(
        name=cycle_in.name,
        start_date=cycle_in.start_date,
        end_date=cycle_in.end_date,
        department_id=cycle_in.department_id,
        location=cycle_in.location,
        status=AuditCycleStatus.DRAFT
    )
    # Assign auditors
    cycle.auditors = auditors
    
    db.add(cycle)
    db.commit()
    db.refresh(cycle)
    
    # Notify assigned auditors
    for auditor in auditors:
        create_notification(
            db, 
            auditor.id, 
            "Assigned to Audit Cycle", 
            f"You have been assigned as an auditor for the cycle '{cycle.name}'.", 
            "AssetAssigned"
        )
        
    log_activity(db, admin.id, "CREATE_AUDIT_CYCLE", {"cycle_id": cycle.id, "name": cycle.name})
    return cycle


@router.post("/cycle/{id}/start", response_model=AuditCycleResponse)
def start_audit_cycle(
    id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(admin_dependency)
):
    """Admin-only: Move audit cycle from DRAFT to ACTIVE."""
    cycle = db.query(AuditCycle).filter(AuditCycle.id == id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Audit cycle not found")
    if cycle.status != AuditCycleStatus.DRAFT:
        raise HTTPException(status_code=400, detail="Only DRAFT cycles can be activated")
        
    cycle.status = AuditCycleStatus.ACTIVE
    db.commit()
    db.refresh(cycle)
    
    log_activity(db, admin.id, "START_AUDIT_CYCLE", {"cycle_id": id})
    return cycle


@router.post("/cycle/{id}/record", response_model=AuditRecordResponse)
def submit_audit_record(
    id: int,
    record_in: AuditRecordCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Auditors: Submit verification status (VERIFIED, MISSING, DAMAGED) for a specific asset."""
    cycle = db.query(AuditCycle).filter(AuditCycle.id == id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Audit cycle not found")
        
    if cycle.status != AuditCycleStatus.ACTIVE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Audit cycle is not currently active"
        )

    # Check permission: User must be an assigned auditor, or an Admin/Asset Manager
    is_auditor = db.query(audit_cycle_auditors).filter_by(audit_cycle_id=id, auditor_id=current_user.id).first()
    is_mgr = current_user.role in [UserRole.ADMIN, UserRole.ASSET_MANAGER]
    if not is_auditor and not is_mgr:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="You are not authorized to submit audits for this cycle"
        )

    # Validate asset exists
    asset = db.query(Asset).filter(Asset.id == record_in.asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    # Check if duplicate record exists in this cycle
    dup = db.query(AuditRecord).filter_by(audit_cycle_id=id, asset_id=record_in.asset_id).first()
    if dup:
        # Update existing record
        dup.status = record_in.status
        dup.notes = record_in.notes
        dup.auditor_id = current_user.id
        dup.audited_at = datetime.utcnow()
        db.commit()
        db.refresh(dup)
        record = dup
    else:
        # Create new record
        record = AuditRecord(
            audit_cycle_id=id,
            asset_id=record_in.asset_id,
            auditor_id=current_user.id,
            status=record_in.status,
            notes=record_in.notes
        )
        db.add(record)
        db.commit()
        db.refresh(record)

    # If discrepancy (missing or damaged), trigger manager alert notifications
    if record_in.status in [AuditRecordStatus.MISSING, AuditRecordStatus.DAMAGED]:
        # Fetch Asset Managers to notify
        managers = db.query(User).filter(User.role == UserRole.ASSET_MANAGER).all()
        for mgr in managers:
            create_notification(
                db, 
                mgr.id, 
                "Audit Discrepancy Flagged", 
                f"Asset {asset.asset_tag} was marked as {record_in.status.value} in cycle '{cycle.name}'.", 
                "AuditDiscrepancy"
            )
            
    log_activity(
        db, 
        current_user.id, 
        "SUBMIT_AUDIT_RECORD", 
        {"cycle_id": id, "asset_id": asset.id, "status": record_in.status.value}
    )
    return record


@router.post("/cycle/{id}/close", response_model=AuditCycleResponse)
def close_audit_cycle(
    id: int,
    db: Session = Depends(get_db),
    manager: User = Depends(manager_or_admin)
):
    """
    Asset Manager / Admin: Close audit cycle.
    Locks the cycle and updates asset statuses (e.g. Lost for missing items, or Damaged etc.).
    """
    cycle = db.query(AuditCycle).filter(AuditCycle.id == id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Audit cycle not found")
        
    if cycle.status != AuditCycleStatus.ACTIVE:
        raise HTTPException(status_code=400, detail="Only ACTIVE cycles can be closed")

    # Lock the cycle
    cycle.status = AuditCycleStatus.CLOSED
    cycle.end_date = datetime.utcnow().date()

    # Update statuses of audited assets
    records = db.query(AuditRecord).filter(AuditRecord.audit_cycle_id == id).all()
    for rec in records:
        asset = db.query(Asset).filter(Asset.id == rec.asset_id).first()
        if asset:
            if rec.status == AuditRecordStatus.MISSING:
                asset.status = AssetStatus.LOST
                # Terminate active allocations if any
                active_alloc = db.query(AssetAllocation).filter_by(asset_id=asset.id, status="ACTIVE").first()
                if active_alloc:
                    active_alloc.status = "RETURNED"
                    active_alloc.returned_at = datetime.utcnow()
                    active_alloc.condition_on_return = "Reported missing during audit"
            elif rec.status == AuditRecordStatus.DAMAGED:
                # Retain damaged notes, set to Under Maintenance or raise repair ticket automatically if desired
                # Let's update asset condition description
                asset.condition = f"DAMAGED: {rec.notes or ''}"
                
    db.commit()
    db.refresh(cycle)

    log_activity(db, manager.id, "CLOSE_AUDIT_CYCLE", {"cycle_id": id})
    return cycle


@router.get("/cycle/{id}/report")
def get_discrepancy_report(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve discrepancies (flagged items: MISSING or DAMAGED) for a cycle."""
    cycle = db.query(AuditCycle).filter(AuditCycle.id == id).first()
    if not cycle:
        raise HTTPException(status_code=404, detail="Audit cycle not found")

    discrepancies = (
        db.query(AuditRecord)
        .filter(
            AuditRecord.audit_cycle_id == id,
            AuditRecord.status.in_([AuditRecordStatus.MISSING, AuditRecordStatus.DAMAGED])
        )
        .all()
    )

    report_list = []
    for record in discrepancies:
        asset = db.query(Asset).filter(Asset.id == record.asset_id).first()
        auditor = db.query(User).filter(User.id == record.auditor_id).first()
        
        report_list.append({
            "record_id": record.id,
            "asset_id": asset.id if asset else None,
            "asset_tag": asset.asset_tag if asset else "Unknown",
            "asset_name": asset.name if asset else "Unknown",
            "pre_audit_status": asset.status.value if asset else "Unknown",
            "audited_status": record.status.value,
            "notes": record.notes,
            "auditor_name": auditor.name if auditor else "System",
            "audited_at": record.audited_at
        })

    return {
        "cycle_name": cycle.name,
        "cycle_status": cycle.status.value,
        "total_discrepancies": len(report_list),
        "discrepancies": report_list
    }


@router.get("/cycles", response_model=List[AuditCycleResponse])
def list_audit_cycles(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List all audit cycles."""
    return db.query(AuditCycle).order_by(AuditCycle.start_date.desc()).all()
