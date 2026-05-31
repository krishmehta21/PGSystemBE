from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, List, Literal
from uuid import UUID
from datetime import date, datetime
from decimal import Decimal

# --- PG Schemas ---
class PGCreate(BaseModel):
    name: str
    address: Optional[str] = None

class PGUpdate(BaseModel):
    name: Optional[str] = None
    address: Optional[str] = None

class PGResponse(BaseModel):
    id: UUID
    name: str
    address: Optional[str] = None
    whatsapp_message_template: str = 'Hi {name}, your rent of ₹{amount} for this month is pending. Please pay today. — {pgName}'
    activation_code: Optional[str] = None
    created_at: datetime
    is_active: bool = True
    subscription_status: Literal["active", "warning", "suspended"] = "active"
    monthly_price: Decimal = Decimal('0.00')
    subscription_start: Optional[date] = None
    subscription_end: Optional[date] = None
    subscription_notes: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class PGSubscriptionUpdate(BaseModel):
    is_active: bool
    subscription_status: Literal["active", "warning", "suspended"]
    monthly_price: Decimal = Decimal('0.00')
    subscription_start: Optional[date] = None
    subscription_end: Optional[date] = None
    subscription_notes: Optional[str] = None

class AdminRevenuePG(BaseModel):
    pg_name: str
    monthly_price: Decimal
    subscription_status: str
    subscription_start: Optional[date]
    subscription_end: Optional[date]
    is_active: bool

class AdminRevenueResponse(BaseModel):
    total_monthly_revenue: Decimal
    active_pg_count: int
    suspended_pg_count: int
    warning_pg_count: int
    pgs: List[AdminRevenuePG]

# --- Room Schemas ---
class RoomCreate(BaseModel):
    pg_id: Optional[UUID] = None
    room_number: str
    total_beds: int

class RoomUpdate(BaseModel):
    room_number: Optional[str] = None
    total_beds: Optional[int] = None

class RoomResponse(BaseModel):
    id: UUID
    pg_id: UUID
    room_number: str
    total_beds: int
    model_config = ConfigDict(from_attributes=True)

class BulkRoomCreate(BaseModel):
    floors: int = Field(..., ge=1, le=20, description="Number of floors")
    rooms_per_floor: int = Field(..., ge=1, le=20, description="Rooms per floor")
    beds_per_room: int = Field(..., ge=1, le=20, description="Beds per room")
    starting_number: int = Field(101, ge=1, description="Starting room number (e.g., 101 → 101,102…201,202…)")

class BulkRoomResult(BaseModel):
    rooms_created: int
    beds_created: int
    skipped_duplicates: List[str]


# --- Bed Schemas ---
class BedCreate(BaseModel):
    room_id: UUID
    bed_label: Optional[str] = None

class BedUpdate(BaseModel):
    bed_label: Optional[str] = None

class BedResponse(BaseModel):
    id: UUID
    room_id: UUID
    bed_label: Optional[str] = None
    is_occupied: bool
    created_at: Optional[datetime] = None
    model_config = ConfigDict(from_attributes=True)

# --- Tenant Schemas ---
class TenantCreate(BaseModel):
    name: str
    phone: str
    rent_amount: Decimal
    bed_id: UUID
    move_in_date: date
    
    aadhaar_last4: Optional[str] = None
    pan_number: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    employer_or_college: Optional[str] = None
    hometown: Optional[str] = None
    food_preference: Optional[Literal["veg", "non_veg", "both"]] = "veg"
    vehicle_registration: Optional[str] = None
    security_deposit_amount: Optional[Decimal] = None
    security_deposit_date: Optional[date] = None
    expected_move_out_date: Optional[date] = None
    police_verification_done: Optional[bool] = False
    police_verification_date: Optional[date] = None
    occupancy_type: Optional[Literal["single", "double", "triple"]] = "single"

class TenantUpdate(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    rent_amount: Optional[Decimal] = None
    move_in_date: Optional[date] = None
    
    aadhaar_last4: Optional[str] = None
    pan_number: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    employer_or_college: Optional[str] = None
    hometown: Optional[str] = None
    food_preference: Optional[Literal["veg", "non_veg", "both"]] = None
    vehicle_registration: Optional[str] = None
    security_deposit_amount: Optional[Decimal] = None
    security_deposit_date: Optional[date] = None
    expected_move_out_date: Optional[date] = None
    police_verification_done: Optional[bool] = None
    police_verification_date: Optional[date] = None
    occupancy_type: Optional[Literal["single", "double", "triple"]] = None

class TenantResponse(BaseModel):
    id: UUID
    name: str
    phone: str
    rent_amount: Decimal
    bed_id: Optional[UUID] = None
    move_in_date: date
    rent_status: Literal["paid", "unpaid"]
    last_paid_date: Optional[date] = None
    created_at: datetime
    
    aadhaar_last4: Optional[str] = None
    pan_number: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    employer_or_college: Optional[str] = None
    hometown: Optional[str] = None
    food_preference: Optional[Literal["veg", "non_veg", "both"]] = "veg"
    vehicle_registration: Optional[str] = None
    security_deposit_amount: Optional[Decimal] = None
    security_deposit_date: Optional[date] = None
    expected_move_out_date: Optional[date] = None
    police_verification_done: Optional[bool] = False
    police_verification_date: Optional[date] = None
    occupancy_type: Optional[Literal["single", "double", "triple"]] = "single"
    
    # Joined fields
    room_number: Optional[str] = None
    bed_label: Optional[str] = None
    
    # Phase 2 Soft Delete & notices
    is_active: bool = True
    notice_given_date: Optional[date] = None
    actual_move_out_date: Optional[date] = None
    deposit_returned_amount: Optional[Decimal] = None
    deposit_deduction_reason: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)

# --- Rent Schemas ---
class RentToggle(BaseModel):
    status: Literal["paid", "unpaid"]

# --- Dashboard Schemas ---
class DashboardResponse(BaseModel):
    pg_name: str
    total_beds: int
    occupied_beds: int
    empty_beds: int
    pending_payments: int
    total_rent_collected: Decimal = Decimal('0.00')
    total_rent_expected: Decimal = Decimal('0.00')
    vacancy_rate: float = 0.00
    beds_vacant_gt30_days: int = 0
    model_config = ConfigDict(from_attributes=True)

# --- Tenant Move-out Schema ---
class TenantMoveOut(BaseModel):
    notice_given_date: Optional[date] = None
    actual_move_out_date: date
    deposit_returned_amount: Decimal
    deposit_deduction_reason: Optional[str] = None

# --- Maintenance Schemas ---
class MaintenanceCreate(BaseModel):
    tenant_id: UUID
    title: str = Field(..., max_length=150)
    description: Optional[str] = None

class MaintenanceUpdate(BaseModel):
    status: Literal["open", "in_progress", "resolved"]

class MaintenanceResponse(BaseModel):
    id: UUID
    pg_id: UUID
    tenant_id: UUID
    bed_id: Optional[UUID] = None
    title: str
    description: Optional[str] = None
    status: Literal["open", "in_progress", "resolved"]
    created_at: datetime
    resolved_at: Optional[datetime] = None
    
    # Joined fields for UI listing
    tenant_name: Optional[str] = None
    room_number: Optional[str] = None
    
    model_config = ConfigDict(from_attributes=True)


class BulkDeleteRequest(BaseModel):
    room_ids: List[UUID]
    force: bool = False

