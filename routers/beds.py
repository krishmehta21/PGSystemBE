from fastapi import APIRouter, HTTPException, Depends, status
from typing import List, Optional
from uuid import UUID
from db.supabase_client import supabase
from models.schemas import BedResponse, BedCreate, BedUpdate
from auth import get_current_user

router = APIRouter(prefix="/beds", tags=["Beds"], dependencies=[Depends(get_current_user)])


def _verify_bed_pg_ownership(bed_id: str, pg_id: str) -> dict:
    """Verify the bed's room belongs to this pg_id. Returns bed row."""
    res = supabase.table("bed") \
        .select("*, room!inner(pg_id)") \
        .eq("id", bed_id) \
        .execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Bed not found")
    bed = res.data[0]
    if str(bed["room"]["pg_id"]) != str(pg_id):
        raise HTTPException(status_code=403, detail="Unauthorized")
    return bed


@router.get("/", response_model=List[BedResponse])
async def list_beds(room_id: Optional[UUID] = None, current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    if room_id:
        # Verify the room belongs to this user's PG
        room_res = supabase.table("room").select("id").eq("id", str(room_id)).eq("pg_id", str(pg_id)).execute()
        if not room_res.data:
            raise HTTPException(status_code=404, detail="Room not found or unauthorized")
        response = supabase.table("bed").select("*").eq("room_id", str(room_id)).execute()
        return response.data or []
    else:
        # Fetch all beds for the active PG in one query
        response = supabase.table("bed").select("*, room!inner(pg_id)").eq("room.pg_id", str(pg_id)).execute()
        # Clean up nested 'room' object to conform to BedResponse model
        data = []
        for b in (response.data or []):
            b_copy = {k: v for k, v in b.items() if k != 'room'}
            data.append(b_copy)
        return data



@router.post("/", response_model=BedResponse, status_code=status.HTTP_201_CREATED)
async def create_bed(bed: BedCreate, current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    # Verify the room belongs to this user's PG
    room_res = supabase.table("room").select("id").eq("id", str(bed.room_id)).eq("pg_id", str(pg_id)).execute()
    if not room_res.data:
        raise HTTPException(status_code=404, detail="Room not found or unauthorized")

    # Count existing beds to auto-label
    existing = supabase.table("bed").select("id").eq("room_id", str(bed.room_id)).execute()
    next_num = len(existing.data or []) + 1
    bed_label = bed.bed_label or f"Bed {next_num}"

    bed_data = {
        "room_id": str(bed.room_id),
        "bed_label": bed_label,
        "is_occupied": False,
    }
    response = supabase.table("bed").insert(bed_data).execute()
    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create bed")
    return response.data[0]


@router.put("/{bed_id}", response_model=BedResponse)
async def update_bed(bed_id: UUID, bed_update: BedUpdate, current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    _verify_bed_pg_ownership(str(bed_id), str(pg_id))

    update_data = bed_update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    response = supabase.table("bed").update(update_data).eq("id", str(bed_id)).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Bed not found")
    return response.data[0]


@router.delete("/{bed_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_bed(bed_id: UUID, current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    bed = _verify_bed_pg_ownership(str(bed_id), str(pg_id))

    if bed.get("is_occupied"):
        raise HTTPException(status_code=400, detail="Cannot delete an occupied bed. Remove the tenant first.")

    supabase.table("bed").delete().eq("id", str(bed_id)).execute()
    return None
