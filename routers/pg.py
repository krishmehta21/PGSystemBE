from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.responses import JSONResponse, StreamingResponse
from typing import List
from uuid import UUID
from db.supabase_client import supabase
from models.schemas import PGCreate, PGUpdate, PGResponse, PGSubscriptionUpdate, AdminRevenueResponse
from decimal import Decimal
from auth import get_current_user
import random
import string
import csv
from io import StringIO
from utils import serialize_decimals

router = APIRouter(prefix="/pgs", tags=["PGs"], dependencies=[Depends(get_current_user)])

@router.get("/debug/user-pg-status")
async def debug_user_pg(current_user: dict = Depends(get_current_user)):
    """
    Returns raw database state for debugging.
    """
    try:
        user_res = supabase.table("users").select("*").eq("id", current_user["id"]).execute()
        if not user_res.data:
            return {"error": "User not found in database"}
            
        user = user_res.data[0]
        pg_id = user.get("pg_id")
        
        pg_exists = False
        if pg_id:
            pg_res = supabase.table("pg_property").select("id").eq("id", pg_id).execute()
            pg_exists = len(pg_res.data) > 0
            
        # Try to find all pgs owned by user if owner_id exists
        all_pgs = []
        try:
            all_pgs_res = supabase.table("pg_property").select("*").eq("owner_id", current_user["id"]).execute()
            all_pgs = all_pgs_res.data if hasattr(all_pgs_res, 'data') else []
        except Exception:
            pass # owner_id might not exist in old schemas
            
        return {
            "user_id": user.get("id"),
            "user_pg_id": pg_id,
            "pg_exists": pg_exists,
            "all_pgs_for_user": all_pgs
        }
    except Exception as e:
         return {"error": str(e)}

@router.get("/me", response_model=PGResponse)
async def get_my_pg(current_user: dict = Depends(get_current_user)):
    """
    Get user's PG with detailed error context.
    
    Error scenarios:
    1. User has no pg_id in database -> "Setup incomplete"
    2. pg_id exists but PG not found -> "Data integrity error"  
    """
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(
            status_code=404, 
            detail="No PG linked. Please set up your PG."
        )
    
    response = supabase.table("pg_property").select("*").eq("id", str(pg_id)).execute()
    if getattr(response, 'error', None):
         raise HTTPException(status_code=500, detail="System error while fetching PG.")
         
    if not response.data:
        raise HTTPException(
            status_code=500, 
            detail="Data integrity error: Linked property not found in database."
        )
    return serialize_decimals(response.data[0])

@router.get("", response_model=List[PGResponse])
async def list_pgs():
    response = supabase.table("pg_property").select("*").execute()
    return serialize_decimals(response.data)

@router.post("", response_model=PGResponse, status_code=status.HTTP_201_CREATED)
async def create_pg(pg: PGCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can create properties.")
        
    try:
        print(f"DEBUG: Admin {current_user.get('id')} creating PG")
        pg_data = pg.model_dump()
        
        # Set admin as creator/owner
        pg_data["owner_id"] = current_user.get("id")
        
        # Generate 6-char auth code
        activation_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        pg_data["activation_code"] = activation_code
        
        response = supabase.table("pg_property").insert(pg_data).execute()
        
        if hasattr(response, 'error') and response.error:
            raise HTTPException(status_code=400, detail=str(response.error))
            
        if not response.data:
            raise HTTPException(status_code=400, detail="Failed to create PG")
        
        new_pg = response.data[0]
        
        # Admins generate PGs to give to Owners. They do NOT link the PG to themselves via pg_id.
        return serialize_decimals(new_pg)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{pg_id}", response_model=PGResponse)
async def get_pg(pg_id: UUID):
    response = supabase.table("pg_property").select("*").eq("id", str(pg_id)).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="PG not found")
        
    return serialize_decimals(response.data[0])

@router.put("/{pg_id}", response_model=PGResponse)
async def update_pg(pg_id: UUID, pg_update: PGUpdate):
    update_data = pg_update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")
        
    response = supabase.table("pg_property").update(update_data).eq("id", str(pg_id)).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="PG not found")
        
    return serialize_decimals(response.data[0])

@router.patch("/{pg_id}/subscription", response_model=PGResponse)
async def update_pg_subscription(pg_id: UUID, sub_update: PGSubscriptionUpdate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can modify subscriptions.")
        
    try:
        update_data = sub_update.model_dump(mode="json", exclude_unset=True)
        if not update_data:
            raise HTTPException(status_code=400, detail="No fields to update")
            
        response = supabase.table("pg_property").update(update_data).eq("id", str(pg_id)).execute()
        
        if not response.data:
            raise HTTPException(status_code=404, detail="PG not found")
            
        return serialize_decimals(response.data[0])
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating subscription: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/{pg_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pg(pg_id: UUID):
    # Check if PG has rooms
    rooms_response = supabase.table("room").select("id").eq("pg_id", str(pg_id)).execute()
    
    if rooms_response.data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Cannot delete PG because it still has rooms. Please delete all rooms first."
        )
        
    supabase.table("pg_property").delete().eq("id", str(pg_id)).execute()
    return None

@router.get("/admin/revenue", response_model=AdminRevenueResponse)
async def get_admin_revenue(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Only admins can view revenue.")
        
    response = supabase.table("pg_property").select("*").execute()
    
    if getattr(response, 'error', None):
         raise HTTPException(status_code=500, detail="Error fetching revenue data")
         
    pgs_data = response.data if response.data else []
    
    total_revenue = Decimal('0.00')
    active_count = 0
    suspended_count = 0
    warning_count = 0
    admin_pgs = []
    
    for pg in pgs_data:
        status = pg.get("subscription_status", "active")
        if status == "active":
            active_count += 1
        elif status == "suspended":
            suspended_count += 1
        elif status == "warning":
            warning_count += 1
            
        is_active = pg.get("is_active", True)
        monthly_price_val = pg.get("monthly_price")
        monthly_price = Decimal(str(monthly_price_val)) if monthly_price_val is not None else Decimal('0.00')
        
        if is_active:
            total_revenue += monthly_price
            
        admin_pgs.append({
            "pg_name": pg.get("name", "Unknown"),
            "monthly_price": monthly_price,
            "subscription_status": status,
            "subscription_start": pg.get("subscription_start"),
            "subscription_end": pg.get("subscription_end"),
            "is_active": is_active
        })
        
    return serialize_decimals({
        "total_monthly_revenue": total_revenue,
        "active_pg_count": active_count,
        "suspended_pg_count": suspended_count,
        "warning_pg_count": warning_count,
        "pgs": admin_pgs
    })


@router.get("/{pg_id}/export/rent-ledger")
async def export_rent_ledger(pg_id: UUID, current_user: dict = Depends(get_current_user)):
    user_pg_id = current_user.get("pg_id")
    if not user_pg_id or str(user_pg_id) != str(pg_id):
        raise HTTPException(status_code=403, detail="Unauthorized to export this property's ledger")
        
    response = supabase.table("tenant") \
        .select("*, bed!inner(bed_label, room!inner(room_number, pg_id))") \
        .eq("bed.room.pg_id", str(pg_id)) \
        .execute()
        
    data = response.data if response.data else []

    f = StringIO()
    writer = csv.writer(f)
    
    writer.writerow([
        "Tenant Name", "Phone", "Room-Bed", "Monthly Rent (INR)", "Status", 
        "Move-in Date", "Hometown", "Food Preference", "Occupancy Type", 
        "Security Deposit (INR)", "Expected Move-out"
    ])
    
    for t in data:
        room_number = t.get("bed", {}).get("room", {}).get("room_number", "N/A")
        bed_label = t.get("bed", {}).get("bed_label", "N/A")
        room_bed = f"{room_number}-{bed_label}"
        
        writer.writerow([
            t.get("name", ""),
            t.get("phone", ""),
            room_bed,
            t.get("rent_amount", 0),
            t.get("rent_status", "").capitalize(),
            t.get("move_in_date", ""),
            t.get("hometown", ""),
            t.get("food_preference", ""),
            t.get("occupancy_type", ""),
            t.get("security_deposit_amount", ""),
            t.get("expected_move_out_date", "")
        ])
        
    f.seek(0)
    
    return StreamingResponse(
        iter([f.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=rent_ledger_{pg_id}.csv"}
    )
