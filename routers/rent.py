from fastapi import APIRouter, HTTPException, Depends
from typing import List, Optional
from uuid import UUID
from datetime import date

from db.supabase_client import supabase
from models.schemas import RentToggle, TenantResponse
from auth import get_current_user

router = APIRouter(prefix="/tenants", tags=["Rent"])


# 🔹 Toggle rent status
@router.patch("/{tenant_id}/rent", response_model=TenantResponse)
async def toggle_rent_status(
    tenant_id: UUID,
    toggle: RentToggle,
    current_user: dict = Depends(get_current_user)
):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    # Verify ownership of the tenant via bed -> room -> pg_id
    verify = supabase.table("tenant").select("bed!inner(room!inner(pg_id))").eq("id", str(tenant_id)).execute()
    if not verify.data or str(verify.data[0]["bed"]["room"]["pg_id"]) != str(pg_id):
         raise HTTPException(status_code=404, detail="Tenant not found or unauthorized")

    update_data = {"rent_status": toggle.status}

    if toggle.status == "paid":
        update_data["last_paid_date"] = str(date.today())
    else:
        update_data["last_paid_date"] = None

    response = supabase.table("tenant") \
        .update(update_data) \
        .eq("id", str(tenant_id)) \
        .execute()

    if getattr(response, 'error', None):
        raise HTTPException(status_code=500, detail=str(response.error))

    if not response.data:
        raise HTTPException(status_code=404, detail="Tenant not found")

    return response.data[0]


# 🔹 Get unpaid tenants
@router.get("/unpaid", response_model=List[TenantResponse])
async def list_unpaid_tenants(
    current_user: dict = Depends(get_current_user)
):
    pg_id = current_user.get("pg_id")

    if not pg_id:
        return []

    # fetch tenants with nested bed + room, filtered by room.pg_id and rent_status
    response = supabase.table("tenant") \
        .select("*, bed!inner(bed_label, room!inner(room_number, pg_id))") \
        .eq("rent_status", "unpaid") \
        .eq("bed.room.pg_id", str(pg_id)) \
        .execute()

    if hasattr(response, 'error') and response.error:
        raise HTTPException(status_code=500, detail=str(response.error))

    results = []

    for t in response.data:
        bed = t.get("bed")
        room = bed.get("room") if bed else None

        if room:
            t["room_number"] = room.get("room_number")
            t["bed_label"] = bed.get("bed_label") if bed else None
            results.append(t)

    return results