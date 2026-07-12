from pydantic import BaseModel, EmailStr, Field, ConfigDict
from typing import Optional, List, Dict, Any
from datetime import datetime, date
from decimal import Decimal
from app.models import UserRole, UserStatus, AssetStatus, BookingStatus, TransferStatus, MaintenancePriority, MaintenanceStatus, AuditCycleStatus, AuditRecordStatus

# ==========================================
# Common Base Config
# ==========================================
class BaseSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

# ==========================================
# User & Auth Schemas
# ==========================================
class UserBase(BaseSchema):
    name: str
    email: EmailStr
    department_id: Optional[int] = None

class UserCreate(UserBase):
    password: str

class UserResponse(UserBase):
    id: int
    role: UserRole
    status: UserStatus
    created_at: datetime
    updated_at: datetime

class UserUpdateRole(BaseSchema):
    role: UserRole

class UserUpdateStatus(BaseSchema):
    status: UserStatus

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class Token(BaseModel):
    access_token: str
    token_type: str
    user: UserResponse

class TokenData(BaseModel):
    email: Optional[str] = None
    role: Optional[UserRole] = None

# ==========================================
# Department Schemas
# ==========================================
class DepartmentBase(BaseSchema):
    name: str
    head_id: Optional[int] = None
    parent_id: Optional[int] = None
    status: UserStatus = UserStatus.ACTIVE

class DepartmentCreate(DepartmentBase):
    pass

class DepartmentUpdate(BaseSchema):
    name: Optional[str] = None
    head_id: Optional[int] = None
    parent_id: Optional[int] = None
    status: Optional[UserStatus] = None

class DepartmentResponse(DepartmentBase):
    id: int
    created_at: datetime
    updated_at: datetime
    # We can fetch nested parent/children in the router if needed

# ==========================================
# Asset Category Schemas
# ==========================================
class CategoryBase(BaseSchema):
    name: str
    fields_schema: Optional[Dict[str, str]] = None  # e.g., {"warranty_period_months": "int", "brand": "str"}

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseSchema):
    name: Optional[str] = None
    fields_schema: Optional[Dict[str, str]] = None

class CategoryResponse(CategoryBase):
    id: int
    created_at: datetime
    updated_at: datetime

# ==========================================
# Asset Schemas
# ==========================================
class AssetBase(BaseSchema):
    name: str
    category_id: int
    serial_number: Optional[str] = None
    acquisition_date: date
    acquisition_cost: Decimal
    condition: str
    location: str
    photo_url: Optional[str] = None
    documents_url: Optional[str] = None
    is_shared_bookable: bool = False
    status: AssetStatus = AssetStatus.AVAILABLE
    category_attributes: Optional[Dict[str, Any]] = None  # Key-values matching schema

class AssetCreate(AssetBase):
    pass

class AssetUpdate(BaseSchema):
    name: Optional[str] = None
    category_id: Optional[int] = None
    serial_number: Optional[str] = None
    acquisition_date: Optional[date] = None
    acquisition_cost: Optional[Decimal] = None
    condition: Optional[str] = None
    location: Optional[str] = None
    photo_url: Optional[str] = None
    documents_url: Optional[str] = None
    is_shared_bookable: Optional[bool] = None
    status: Optional[AssetStatus] = None
    category_attributes: Optional[Dict[str, Any]] = None

class AssetResponse(AssetBase):
    id: int
    asset_tag: str
    created_at: datetime
    updated_at: datetime

# ==========================================
# Allocation & Transfer Schemas
# ==========================================
class AllocationBase(BaseSchema):
    asset_id: int
    allocated_to_user_id: Optional[int] = None
    allocated_to_department_id: Optional[int] = None
    expected_return_date: Optional[date] = None

class AllocationCreate(AllocationBase):
    pass

class AllocationResponse(AllocationBase):
    id: int
    returned_at: Optional[datetime] = None
    condition_on_return: Optional[str] = None
    return_approved_by_id: Optional[int] = None
    status: str
    created_at: datetime

class AssetReturnRequest(BaseSchema):
    condition_on_return: str

class TransferRequestCreate(BaseSchema):
    asset_id: int
    to_user_id: Optional[int] = None
    to_department_id: Optional[int] = None

class TransferRequestResponse(BaseSchema):
    id: int
    asset_id: int
    from_user_id: Optional[int] = None
    from_department_id: Optional[int] = None
    to_user_id: Optional[int] = None
    to_department_id: Optional[int] = None
    requested_by_id: int
    approved_by_id: Optional[int] = None
    status: TransferStatus
    created_at: datetime
    updated_at: datetime

# ==========================================
# Resource Booking Schemas
# ==========================================
class BookingBase(BaseSchema):
    asset_id: int
    start_time: datetime
    end_time: datetime

class BookingCreate(BookingBase):
    pass

class BookingReschedule(BaseSchema):
    start_time: datetime
    end_time: datetime

class BookingResponse(BookingBase):
    id: int
    user_id: int
    status: BookingStatus
    created_at: datetime
    updated_at: datetime

# ==========================================
# Maintenance Schemas
# ==========================================
class MaintenanceBase(BaseSchema):
    asset_id: int
    description: str
    priority: MaintenancePriority = MaintenancePriority.MEDIUM
    photo_url: Optional[str] = None

class MaintenanceCreate(MaintenanceBase):
    pass

class MaintenanceUpdate(BaseSchema):
    description: Optional[str] = None
    priority: Optional[MaintenancePriority] = None
    photo_url: Optional[str] = None
    status: Optional[MaintenanceStatus] = None
    technician_id: Optional[int] = None

class MaintenanceResponse(MaintenanceBase):
    id: int
    raised_by_id: int
    status: MaintenanceStatus
    technician_id: Optional[int] = None
    approved_by_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

# ==========================================
# Audit Cycle & Records Schemas
# ==========================================
class AuditCycleBase(BaseSchema):
    name: str
    start_date: date
    end_date: date
    department_id: Optional[int] = None
    location: Optional[str] = None

class AuditCycleCreate(AuditCycleBase):
    auditor_ids: List[int]

class AuditCycleResponse(AuditCycleBase):
    id: int
    status: AuditCycleStatus
    created_at: datetime
    updated_at: datetime

class AuditRecordCreate(BaseSchema):
    asset_id: int
    status: AuditRecordStatus
    notes: Optional[str] = None

class AuditRecordResponse(BaseSchema):
    id: int
    audit_cycle_id: int
    asset_id: int
    auditor_id: Optional[int] = None
    status: AuditRecordStatus
    notes: Optional[str] = None
    audited_at: datetime

# ==========================================
# Notifications & Activity Logs
# ==========================================
class NotificationResponse(BaseSchema):
    id: int
    user_id: int
    title: str
    message: str
    type: str
    is_read: bool
    created_at: datetime

class ActivityLogResponse(BaseSchema):
    id: int
    user_id: Optional[int] = None
    action: str
    details: Optional[Dict[str, Any]] = None
    created_at: datetime

# ==========================================
# Dashboard & Analytics Schemas
# ==========================================
class DashboardKPICards(BaseSchema):
    assets_available: int
    assets_allocated: int
    maintenance_today: int
    active_bookings: int
    pending_transfers: int
    upcoming_returns: int

class DashboardData(BaseSchema):
    kpis: DashboardKPICards
    overdue_returns: List[AllocationResponse]
    upcoming_returns: List[AllocationResponse]
