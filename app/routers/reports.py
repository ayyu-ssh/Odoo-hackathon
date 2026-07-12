from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import func, desc
from typing import List, Dict, Any
import csv
import io
from app.db import get_db
from app.models import Asset, AssetAllocation, MaintenanceRequest, ResourceBooking, Department, AssetCategory, User, UserRole
from app.auth import get_current_user, require_role

router = APIRouter(prefix="/reports", tags=["Reports & Analytics"])

# Only Admins and Asset Managers can access reporting
manager_dependency = require_role([UserRole.ADMIN, UserRole.ASSET_MANAGER])

@router.get("/utilization")
def get_utilization_trends(
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """Retrieve asset utilization trends: most-allocated assets versus idle ones."""
    # Active/past allocation counts per asset
    alloc_counts = (
        db.query(Asset.id, Asset.name, Asset.asset_tag, func.count(AssetAllocation.id).label("allocation_count"))
        .outerjoin(AssetAllocation, AssetAllocation.asset_id == Asset.id)
        .group_by(Asset.id)
        .order_by(desc("allocation_count"))
        .all()
    )

    most_used = [{"id": r[0], "name": r[1], "tag": r[2], "allocations": r[3]} for r in alloc_counts[:10]]
    idle = [{"id": r[0], "name": r[1], "tag": r[2], "allocations": r[3]} for r in alloc_counts if r[3] == 0]

    return {
        "most_used": most_used,
        "idle_assets": idle,
        "total_active_assets": db.query(Asset).count()
    }


@router.get("/maintenance")
def get_maintenance_frequency(
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """Analyze repair frequencies grouped by individual assets and category levels."""
    # Group by Asset
    asset_maint = (
        db.query(Asset.asset_tag, Asset.name, func.count(MaintenanceRequest.id).label("request_count"))
        .join(MaintenanceRequest, MaintenanceRequest.asset_id == Asset.id)
        .group_by(Asset.id)
        .order_by(desc("request_count"))
        .all()
    )

    # Group by Category
    category_maint = (
        db.query(AssetCategory.name, func.count(MaintenanceRequest.id).label("request_count"))
        .join(Asset, Asset.category_id == AssetCategory.id)
        .join(MaintenanceRequest, MaintenanceRequest.asset_id == Asset.id)
        .group_by(AssetCategory.id)
        .order_by(desc("request_count"))
        .all()
    )

    return {
        "by_asset": [{"tag": r[0], "name": r[1], "count": r[2]} for r in asset_maint],
        "by_category": [{"category": r[0], "count": r[1]} for r in category_maint]
    }


@router.get("/retirement")
def get_retirement_and_lifecycle_alerts(
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """Identify assets nearing expected end-of-life or showing excessive wear and tear."""
    # Assets in POOR condition, or showing high maintenance counts
    flagged_condition = (
        db.query(Asset.id, Asset.name, Asset.asset_tag, Asset.condition, Asset.acquisition_date)
        .filter(Asset.condition.ilike("%poor%") | Asset.condition.ilike("%damaged%"))
        .all()
    )

    # Retrieve assets with more than 3 repair requests
    high_maintenance = (
        db.query(Asset.id, Asset.name, Asset.asset_tag, func.count(MaintenanceRequest.id).label("count"))
        .join(MaintenanceRequest, MaintenanceRequest.asset_id == Asset.id)
        .group_by(Asset.id)
        .having(func.count(MaintenanceRequest.id) >= 3)
        .all()
    )

    return {
        "nearing_retirement_or_poor_condition": [
            {"id": r[0], "name": r[1], "tag": r[2], "condition": r[3], "acquired": r[4]}
            for r in flagged_condition
        ],
        "excessive_repairs_needed": [
            {"id": r[0], "name": r[1], "tag": r[2], "maintenance_count": r[3]}
            for r in high_maintenance
        ]
    }


@router.get("/allocations")
def get_department_allocations(
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """Aggregate distribution counts summarizing how many assets belong to each department."""
    dept_summary = (
        db.query(Department.name, func.count(AssetAllocation.id))
        .join(AssetAllocation, AssetAllocation.allocated_to_department_id == Department.id)
        .filter(AssetAllocation.status == "ACTIVE")
        .group_by(Department.id)
        .all()
    )

    # Employee-based allocations group by department
    emp_summary = (
        db.query(Department.name, func.count(AssetAllocation.id))
        .join(User, User.department_id == Department.id)
        .join(AssetAllocation, AssetAllocation.allocated_to_user_id == User.id)
        .filter(AssetAllocation.status == "ACTIVE")
        .group_by(Department.id)
        .all()
    )

    res = {}
    for r in dept_summary:
        res[r[0]] = res.get(r[0], 0) + r[1]
    for r in emp_summary:
        res[r[0]] = res.get(r[0], 0) + r[1]

    return [{"department": k, "active_allocations": v} for k, v in res.items()]


@router.get("/heatmap")
def get_resource_booking_heatmap(
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """Provide weekday/hourly aggregated heatmaps for peak booking times."""
    bookings = db.query(ResourceBooking.start_time).all()
    
    # We will construct a simple heatmap model of days of week (0-6) and hours (0-23)
    # Day 0 = Monday, Day 6 = Sunday
    heatmap = {}
    for b in bookings:
        dt = b[0]
        day = dt.strftime("%A")
        hour = dt.hour
        key = f"{day} {hour:02d}:00"
        heatmap[key] = heatmap.get(key, 0) + 1

    # Sort heatmap for readability
    sorted_heatmap = [{"slot": k, "bookings_count": v} for k, v in sorted(heatmap.items(), key=lambda x: x[1], reverse=True)]
    return {"peak_slots": sorted_heatmap[:15]}


@router.get("/export/assets")
def export_assets_report_csv(
    db: Session = Depends(get_db),
    manager: User = Depends(manager_dependency)
):
    """Export the asset directory in standard CSV format."""
    assets = db.query(Asset).all()

    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header
    writer.writerow([
        "Asset Tag", "Asset Name", "Serial Number", 
        "Acquisition Date", "Acquisition Cost", "Condition", 
        "Location", "Shared Bookable", "Status"
    ])
    
    for a in assets:
        writer.writerow([
            a.asset_tag, a.name, a.serial_number or "N/A",
            a.acquisition_date, a.acquisition_cost, a.condition,
            a.location, a.is_shared_bookable, a.status.value
        ])
        
    output.seek(0)
    
    headers = {
        'Content-Disposition': 'attachment; filename="assetflow_assets_report.csv"'
    }
    return StreamingResponse(io.BytesIO(output.getvalue().encode("utf-8")), media_type="text/csv", headers=headers)
