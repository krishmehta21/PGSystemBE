from fastapi import APIRouter, HTTPException, status, Depends
from typing import List, Optional
from uuid import UUID
from datetime import datetime
from db.supabase_client import supabase
from models.schemas import MaintenanceCreate, MaintenanceUpdate, MaintenanceResponse
from auth import get_current_user

router = APIRouter(prefix="/maintenance", tags=["Maintenance"], dependencies=[Depends(get_current_user)])

@router.get("/", response_model=List[MaintenanceResponse])
async def list_maintenance(current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    try:
        response = supabase.table("maintenance_request") \
            .select("*, tenant(name), bed(room(room_number))") \
            .eq("pg_id", str(pg_id)) \
            .order("created_at", desc=True) \
            .execute()

        results = []
        for t in response.data:
            # Extract tenant name
            tenant_info = t.get("tenant") or {}
            t["tenant_name"] = tenant_info.get("name") if isinstance(tenant_info, dict) else None

            # Extract room number
            bed_info = t.get("bed") or {}
            room_info = bed_info.get("room") or {} if isinstance(bed_info, dict) else {}
            t["room_number"] = room_info.get("room_number") if isinstance(room_info, dict) else None

            results.append(t)
        return results
    except Exception as e:
        print(f"Error listing maintenance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/", response_model=MaintenanceResponse, status_code=status.HTTP_201_CREATED)
async def create_maintenance(
    payload: MaintenanceCreate,
    current_user: dict = Depends(get_current_user)
):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    # Verify that tenant belongs to this PG
    try:
        verify = supabase.table("tenant") \
            .select("name, bed_id, bed!inner(room!inner(pg_id, room_number))") \
            .eq("id", str(payload.tenant_id)) \
            .execute()
    except Exception as e:
        print(f"Error verifying tenant: {e}")
        raise HTTPException(status_code=404, detail="Tenant not found or unauthorized")

    if not verify.data:
        raise HTTPException(status_code=404, detail="Tenant not found or does not belong to this property")

    tenant_record = verify.data[0]
    # Check if the tenant belongs to the active PG
    bed_data = tenant_record.get("bed") or {}
    room_data = bed_data.get("room") or {}
    if str(room_data.get("pg_id")) != str(pg_id):
        raise HTTPException(status_code=404, detail="Tenant does not belong to your property")

    tenant_name = tenant_record.get("name")
    room_number = room_data.get("room_number")
    bed_id = tenant_record.get("bed_id")

    insert_data = {
        "pg_id": str(pg_id),
        "tenant_id": str(payload.tenant_id),
        "bed_id": str(bed_id) if bed_id else None,
        "title": payload.title,
        "description": payload.description,
        "status": "open"
    }

    try:
        response = supabase.table("maintenance_request").insert(insert_data).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to create maintenance ticket")
        
        ticket = response.data[0]
        ticket["tenant_name"] = tenant_name
        ticket["room_number"] = room_number
        return ticket
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error creating maintenance: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@router.patch("/{id}", response_model=MaintenanceResponse)
async def update_maintenance(
    id: UUID,
    payload: MaintenanceUpdate,
    current_user: dict = Depends(get_current_user)
):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    # Validate ownership of the ticket
    try:
        verify_ticket = supabase.table("maintenance_request") \
            .select("pg_id") \
            .eq("id", str(id)) \
            .execute()
    except Exception as e:
        print(f"Error verifying ticket: {e}")
        raise HTTPException(status_code=404, detail="Maintenance ticket not found")

    if not verify_ticket.data or str(verify_ticket.data[0].get("pg_id")) != str(pg_id):
        raise HTTPException(status_code=404, detail="Maintenance ticket not found or unauthorized")

    # Prepare update payload
    resolved_at = datetime.utcnow().isoformat() if payload.status == "resolved" else None
    update_data = {
        "status": payload.status,
        "resolved_at": resolved_at
    }

    try:
        update_response = supabase.table("maintenance_request") \
            .update(update_data) \
            .eq("id", str(id)) \
            .execute()
            
        if not update_response.data:
            raise HTTPException(status_code=500, detail="Failed to update maintenance ticket")

        # Query full ticket details to include tenant and room info
        ticket_res = supabase.table("maintenance_request") \
            .select("*, tenant(name), bed(room(room_number))") \
            .eq("id", str(id)) \
            .execute()

        if not ticket_res.data:
            raise HTTPException(status_code=500, detail="Failed to fetch updated ticket details")

        ticket = ticket_res.data[0]
        
        # Populate tenant name and room number
        tenant_info = ticket.get("tenant") or {}
        ticket["tenant_name"] = tenant_info.get("name") if isinstance(tenant_info, dict) else None

        bed_info = ticket.get("bed") or {}
        room_info = bed_info.get("room") or {} if isinstance(bed_info, dict) else {}
        ticket["room_number"] = room_info.get("room_number") if isinstance(room_info, dict) else None

        return ticket
    except HTTPException:
        raise
    except Exception as e:
        print(f"Error updating maintenance: {e}")
        raise HTTPException(status_code=500, detail=str(e))
