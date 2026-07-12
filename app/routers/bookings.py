from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from sqlalchemy import and_
from typing import List, Optional
from app.db import get_db
from app.models import Asset, ResourceBooking, User, UserRole, BookingStatus
from app.schemas import BookingCreate, BookingResponse, BookingReschedule
from app.auth import get_current_user
from app.crud import log_activity, create_notification

router = APIRouter(prefix="/bookings", tags=["Resource Bookings"])

def check_booking_overlap(
    db: Session, 
    asset_id: int, 
    start_time: datetime, 
    end_time: datetime, 
    exclude_booking_id: Optional[int] = None
) -> bool:
    """
    Checks if a bookable asset is already reserved in the specified time frame.
    Overlaps occur when S1 < E2 and E1 > S2.
    """
    query = db.query(ResourceBooking).filter(
        ResourceBooking.asset_id == asset_id,
        ResourceBooking.status != BookingStatus.CANCELLED,
        ResourceBooking.start_time < end_time,
        ResourceBooking.end_time > start_time
    )
    if exclude_booking_id:
        query = query.filter(ResourceBooking.id != exclude_booking_id)
        
    return query.count() > 0


@router.post("/", response_model=BookingResponse, status_code=status.HTTP_201_CREATED)
def create_booking(
    booking_in: BookingCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Book a shared resource with strict time slot overlap checks."""
    # Retrieve asset and ensure it is bookable
    asset = db.query(Asset).filter(Asset.id == booking_in.asset_id).first()
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
        
    if not asset.is_shared_bookable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This asset is not flagged as a shared, bookable resource."
        )

    # Time validation
    if booking_in.start_time >= booking_in.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Start time must be before end time"
        )
        
    if booking_in.start_time < datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Cannot book a time slot in the past"
        )

    # Check for overlaps
    if check_booking_overlap(db, asset.id, booking_in.start_time, booking_in.end_time):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Time slot overlap! Another reservation already exists for this slot."
        )

    booking = ResourceBooking(
        asset_id=booking_in.asset_id,
        user_id=current_user.id,
        start_time=booking_in.start_time,
        end_time=booking_in.end_time,
        status=BookingStatus.UPCOMING
    )
    db.add(booking)
    db.commit()
    db.refresh(booking)

    log_activity(db, current_user.id, "CREATE_BOOKING", {"booking_id": booking.id})
    return booking


@router.get("/calendar", response_model=List[BookingResponse])
def get_calendar(
    asset_id: int,
    start: Optional[datetime] = Query(None, description="Start range filtering"),
    end: Optional[datetime] = Query(None, description="End range filtering"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Retrieve bookings for a resource to display in a calendar format."""
    query = db.query(ResourceBooking).filter(
        ResourceBooking.asset_id == asset_id,
        ResourceBooking.status != BookingStatus.CANCELLED
    )
    if start:
        query = query.filter(ResourceBooking.end_time >= start)
    if end:
        query = query.filter(ResourceBooking.start_time <= end)
        
    return query.order_by(ResourceBooking.start_time).all()


@router.put("/{id}/cancel", response_model=BookingResponse)
def cancel_booking(
    id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cancel an upcoming reservation. Available only to owner or management."""
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Access check: Owner, Admin, or Asset Manager
    if (
        booking.user_id != current_user.id and 
        current_user.role not in [UserRole.ADMIN, UserRole.ASSET_MANAGER]
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authorized to cancel this booking"
        )

    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Booking is already cancelled")

    booking.status = BookingStatus.CANCELLED
    db.commit()
    db.refresh(booking)

    log_activity(db, current_user.id, "CANCEL_BOOKING", {"booking_id": id})
    return booking


@router.put("/{id}/reschedule", response_model=BookingResponse)
def reschedule_booking(
    id: int,
    res_in: BookingReschedule,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Reschedule booking with overlap checks. Available only to owner or management."""
    booking = db.query(ResourceBooking).filter(ResourceBooking.id == id).first()
    if not booking:
        raise HTTPException(status_code=404, detail="Booking not found")

    # Access check
    if (
        booking.user_id != current_user.id and 
        current_user.role not in [UserRole.ADMIN, UserRole.ASSET_MANAGER]
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, 
            detail="Not authorized to reschedule this booking"
        )

    if booking.status == BookingStatus.CANCELLED:
        raise HTTPException(status_code=400, detail="Cannot reschedule a cancelled booking")

    # Time validation
    if res_in.start_time >= res_in.end_time:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Start time must be before end time"
        )

    # Check for overlaps excluding the current booking itself
    if check_booking_overlap(db, booking.asset_id, res_in.start_time, res_in.end_time, exclude_booking_id=id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Time slot overlap! Another reservation already exists for this slot."
        )

    booking.start_time = res_in.start_time
    booking.end_time = res_in.end_time
    # Reset status if it was completed or ongoing (reschedule into future)
    booking.status = BookingStatus.UPCOMING

    db.commit()
    db.refresh(booking)

    log_activity(db, current_user.id, "RESCHEDULE_BOOKING", {"booking_id": id})
    return booking
