from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from app.db import get_db
from app.models import (
    Asset,
    AssetAllocation,
    MaintenanceRequest,
    ResourceBooking,
    TransferRequest,
    User,
    UserRole,
    AssetStatus,
    BookingStatus,
    TransferStatus,
    MaintenanceStatus
)
from app.schemas import DashboardData, DashboardKPICards, AllocationResponse
from app.auth import get_current_user

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])

@router.get("/", response_model=DashboardData)
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve live snapshot of KPIs, overdue returns, and upcoming returns scoped by role."""
    today = datetime.utcnow().date()
    seven_days_later = today + timedelta(days=7)

    # 1. Gather stats based on user role
    # Asset Managers & Admins see global metrics
    # Department Heads see department-level metrics
    # Employees see their own items

    # KPI counts:
    # Assets counts
    if current_user.role in [UserRole.ADMIN, UserRole.ASSET_MANAGER]:
        avail_count = db.query(Asset).filter(Asset.status == AssetStatus.AVAILABLE).count()
        alloc_count = db.query(Asset).filter(Asset.status == AssetStatus.ALLOCATED).count()
    elif current_user.role == UserRole.DEPARTMENT_HEAD:
        # Managed department IDs
        managed_dept_ids = [d.id for d in current_user.headed_departments]
        
        # Available assets (global pool, bookable/allocatable to department)
        avail_count = db.query(Asset).filter(Asset.status == AssetStatus.AVAILABLE).count()
        
        # Allocated to this department (either to dept directly or to employee in dept)
        alloc_count = (
            db.query(AssetAllocation)
            .outerjoin(User, AssetAllocation.allocated_to_user_id == User.id)
            .filter(
                AssetAllocation.status == "ACTIVE",
                (AssetAllocation.allocated_to_department_id.in_(managed_dept_ids)) |
                (User.department_id.in_(managed_dept_ids))
            )
            .count()
        )
    else:
        # Employee
        avail_count = db.query(Asset).filter(Asset.status == AssetStatus.AVAILABLE, Asset.is_shared_bookable == True).count()
        alloc_count = db.query(AssetAllocation).filter(
            AssetAllocation.allocated_to_user_id == current_user.id,
            AssetAllocation.status == "ACTIVE"
        ).count()

    # Maintenance today (technician assigned or in progress)
    maint_query = db.query(MaintenanceRequest).filter(
        MaintenanceRequest.status.in_([
            MaintenanceStatus.APPROVED, 
            MaintenanceStatus.TECHNICIAN_ASSIGNED, 
            MaintenanceStatus.IN_PROGRESS
        ])
    )
    if current_user.role == UserRole.EMPLOYEE:
        maint_count = maint_query.filter(
            (MaintenanceRequest.raised_by_id == current_user.id) | 
            (MaintenanceRequest.technician_id == current_user.id)
        ).count()
    elif current_user.role == UserRole.DEPARTMENT_HEAD:
        managed_dept_ids = [d.id for d in current_user.headed_departments]
        maint_count = maint_query.join(User, MaintenanceRequest.raised_by_id == User.id).filter(
            User.department_id.in_(managed_dept_ids)
        ).count()
    else:
        maint_count = maint_query.count()

    # Active bookings (Upcoming or Ongoing)
    booking_query = db.query(ResourceBooking).filter(
        ResourceBooking.status.in_([BookingStatus.UPCOMING, BookingStatus.ONGOING])
    )
    if current_user.role == UserRole.EMPLOYEE:
        booking_count = booking_query.filter(ResourceBooking.user_id == current_user.id).count()
    elif current_user.role == UserRole.DEPARTMENT_HEAD:
        managed_dept_ids = [d.id for d in current_user.headed_departments]
        booking_count = booking_query.join(User, ResourceBooking.user_id == User.id).filter(
            User.department_id.in_(managed_dept_ids)
        ).count()
    else:
        booking_count = booking_query.count()

    # Pending transfers
    transfer_query = db.query(TransferRequest).filter(TransferRequest.status == TransferStatus.PENDING)
    if current_user.role == UserRole.EMPLOYEE:
        transfer_count = transfer_query.filter(
            (TransferRequest.requested_by_id == current_user.id) | 
            (TransferRequest.from_user_id == current_user.id) | 
            (TransferRequest.to_user_id == current_user.id)
        ).count()
    elif current_user.role == UserRole.DEPARTMENT_HEAD:
        managed_dept_ids = [d.id for d in current_user.headed_departments]
        transfer_count = transfer_query.filter(
            (TransferRequest.from_department_id.in_(managed_dept_ids)) |
            (TransferRequest.to_department_id.in_(managed_dept_ids))
        ).count()
    else:
        transfer_count = transfer_query.count()

    # Overdue and upcoming returns queries
    alloc_base = db.query(AssetAllocation).filter(AssetAllocation.status == "ACTIVE")
    if current_user.role == UserRole.EMPLOYEE:
        alloc_base = alloc_base.filter(AssetAllocation.allocated_to_user_id == current_user.id)
    elif current_user.role == UserRole.DEPARTMENT_HEAD:
        managed_dept_ids = [d.id for d in current_user.headed_departments]
        alloc_base = alloc_base.outerjoin(User, AssetAllocation.allocated_to_user_id == User.id).filter(
            (AssetAllocation.allocated_to_department_id.in_(managed_dept_ids)) |
            (User.department_id.in_(managed_dept_ids))
        )

    # Overdue returns: return date in the past
    overdue_list = alloc_base.filter(AssetAllocation.expected_return_date < today).all()
    # Upcoming returns: return date within next 7 days (and not overdue)
    upcoming_list = alloc_base.filter(
        AssetAllocation.expected_return_date >= today,
        AssetAllocation.expected_return_date <= seven_days_later
    ).all()

    kpi_cards = DashboardKPICards(
        assets_available=avail_count,
        assets_allocated=alloc_count,
        maintenance_today=maint_count,
        active_bookings=booking_count,
        pending_transfers=transfer_count,
        upcoming_returns=len(overdue_list) + len(upcoming_list) # count of overall returns expected/overdue
    )

    return {
        "kpis": kpi_cards,
        "overdue_returns": overdue_list,
        "upcoming_returns": upcoming_list
    }
