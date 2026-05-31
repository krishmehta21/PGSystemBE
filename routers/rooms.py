from fastapi import APIRouter, HTTPException, Depends, status
from typing import List
from uuid import UUID
from db.supabase_client import supabase
from models.schemas import RoomCreate, RoomUpdate, RoomResponse, BulkRoomCreate, BulkRoomResult, BulkDeleteRequest
from auth import get_current_user

router = APIRouter(prefix="/rooms", tags=["Rooms"], dependencies=[Depends(get_current_user)])



def _verify_room_ownership(room_id: str, pg_id: str) -> dict:
    """Returns the room if it belongs to this pg_id, else raises 404."""
    res = supabase.table("room").select("*").eq("id", room_id).eq("pg_id", pg_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Room not found or unauthorized")
    return res.data[0]


@router.get("/", response_model=List[RoomResponse])
async def list_rooms(current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        return []
    response = supabase.table("room").select("*").eq("pg_id", str(pg_id)).order("room_number").execute()
    return response.data


@router.get("/{room_id}", response_model=RoomResponse)
async def get_room(room_id: UUID, current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")
    return _verify_room_ownership(str(room_id), str(pg_id))


@router.post("/", response_model=RoomResponse, status_code=status.HTTP_201_CREATED)
async def create_room(room: RoomCreate, current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    # Duplicate check
    existing = supabase.table("room") \
        .select("id") \
        .eq("pg_id", str(pg_id)) \
        .eq("room_number", room.room_number.strip()) \
        .execute()
    if existing.data:
        raise HTTPException(status_code=400, detail=f"Room {room.room_number} already exists")

    room_data = room.model_dump()
    room_data["pg_id"] = str(pg_id)
    room_data["room_number"] = room_data["room_number"].strip()
    response = supabase.table("room").insert(room_data).execute()

    if not response.data:
        raise HTTPException(status_code=500, detail="Failed to create room")

    new_room = response.data[0]
    room_id = new_room["id"]

    # Auto-create beds
    beds = [{"room_id": room_id, "bed_label": f"Bed {i}", "is_occupied": False}
            for i in range(1, room.total_beds + 1)]
    if beds:
        supabase.table("bed").insert(beds).execute()

    return new_room


@router.put("/{room_id}", response_model=RoomResponse)
async def update_room(room_id: UUID, room_update: RoomUpdate, current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    _verify_room_ownership(str(room_id), str(pg_id))

    update_data = room_update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    if "room_number" in update_data:
        update_data["room_number"] = update_data["room_number"].strip()
        # Duplicate check (exclude self)
        dup = supabase.table("room") \
            .select("id") \
            .eq("pg_id", str(pg_id)) \
            .eq("room_number", update_data["room_number"]) \
            .neq("id", str(room_id)) \
            .execute()
        if dup.data:
            raise HTTPException(status_code=400, detail=f"Room {update_data['room_number']} already exists")

    response = supabase.table("room").update(update_data).eq("id", str(room_id)).eq("pg_id", str(pg_id)).execute()
    if not response.data:
        raise HTTPException(status_code=404, detail="Room not found or unauthorized")
    return response.data[0]


@router.delete("/{room_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_room(room_id: UUID, force: bool = False, current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    _verify_room_ownership(str(room_id), str(pg_id))

    # Check for tenants in this room's beds
    occupied = supabase.table("tenant") \
        .select("id") \
        .eq("bed.room_id", str(room_id)) \
        .execute()

    # A safer check: get beds, then check if any is occupied
    beds_res = supabase.table("bed").select("id, is_occupied").eq("room_id", str(room_id)).execute()
    occupied_beds = [b for b in (beds_res.data or []) if b["is_occupied"]]

    if occupied_beds and not force:
        raise HTTPException(
            status_code=409,
            detail=f"Room has {len(occupied_beds)} occupied bed(s). Remove tenants first, or use force=true."
        )

    # Delete tenants → beds → room (cascade-safe if DB doesn't enforce it)
    if occupied_beds:
        for bed in occupied_beds:
            supabase.table("tenant").delete().eq("bed_id", bed["id"]).execute()

    supabase.table("bed").delete().eq("room_id", str(room_id)).execute()
    supabase.table("room").delete().eq("id", str(room_id)).eq("pg_id", str(pg_id)).execute()

    return None


@router.post("/bulk", response_model=BulkRoomResult, status_code=status.HTTP_201_CREATED)
async def bulk_create_rooms(payload: BulkRoomCreate, current_user: dict = Depends(get_current_user)):
    """
    Create multiple rooms across N floors in one request.

    Room numbers are generated as: floor_prefix * 100 + room_index
    e.g. starting_number=101, floors=3, rooms_per_floor=4
    → 101,102,103,104 | 201,202,203,204 | 301,302,303,304
    """
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    # Determine the floor number of the starting_number
    # e.g. 101 → floor_base=1, 201 → floor_base=2
    start = payload.starting_number
    floor_base = start // 100          # floor prefix (1 for 101, 2 for 201)
    room_base  = start % 100           # starting room index within the floor (1 for 101)

    # Generate all candidate room numbers
    candidate_numbers: list[str] = []
    for floor_offset in range(payload.floors):
        floor = floor_base + floor_offset
        for room_offset in range(payload.rooms_per_floor):
            room_index = room_base + room_offset
            candidate_numbers.append(str(floor * 100 + room_index))

    # Fetch existing rooms for this PG to detect duplicates
    existing_res = supabase.table("room") \
        .select("room_number") \
        .eq("pg_id", str(pg_id)) \
        .execute()
    existing_numbers = {r["room_number"] for r in (existing_res.data or [])}

    # Split candidates into to-create and skipped
    to_create    = [n for n in candidate_numbers if n not in existing_numbers]
    skipped      = [n for n in candidate_numbers if n in existing_numbers]

    if not to_create:
        raise HTTPException(
            status_code=400,
            detail=f"All {len(candidate_numbers)} rooms already exist. Nothing to create."
        )

    # Batch insert rooms
    rooms_payload = [
        {"pg_id": str(pg_id), "room_number": num, "total_beds": payload.beds_per_room}
        for num in to_create
    ]
    rooms_res = supabase.table("room").insert(rooms_payload).execute()
    if not rooms_res.data:
        raise HTTPException(status_code=500, detail="Failed to create rooms")

    created_rooms = rooms_res.data  # list of {id, room_number, ...}

    # Batch insert beds for every created room
    beds_payload = []
    for room in created_rooms:
        for i in range(1, payload.beds_per_room + 1):
            beds_payload.append({
                "room_id": room["id"],
                "bed_label": f"Bed {i}",
                "is_occupied": False,
            })

    beds_created = 0
    if beds_payload:
        beds_res = supabase.table("bed").insert(beds_payload).execute()
        beds_created = len(beds_res.data or [])

    return BulkRoomResult(
        rooms_created=len(created_rooms),
        beds_created=beds_created,
        skipped_duplicates=skipped,
    )


@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
async def bulk_delete_rooms(payload: BulkDeleteRequest, current_user: dict = Depends(get_current_user)):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    room_ids_str = [str(rid) for rid in payload.room_ids]
    if not room_ids_str:
        return None

    # Verify all rooms belong to this PG
    rooms_res = supabase.table("room").select("id").in_("id", room_ids_str).eq("pg_id", str(pg_id)).execute()
    verified_ids = [r["id"] for r in (rooms_res.data or [])]
    if len(verified_ids) != len(room_ids_str):
        raise HTTPException(status_code=403, detail="Some rooms are unauthorized or not found")

    # Check occupied beds in these rooms
    beds_res = supabase.table("bed").select("id, room_id, is_occupied").in_("room_id", verified_ids).execute()
    occupied_beds = [b for b in (beds_res.data or []) if b["is_occupied"]]

    if occupied_beds and not payload.force:
        raise HTTPException(
            status_code=409,
            detail=f"Selected rooms have {len(occupied_beds)} occupied bed(s). Remove tenants first, or use force=true."
        )

    # Delete tenants in occupied beds if forcing
    if occupied_beds:
        occupied_bed_ids = [b["id"] for b in occupied_beds]
        supabase.table("tenant").delete().in_("bed_id", occupied_bed_ids).execute()

    # Delete all beds in these rooms
    supabase.table("bed").delete().in_("room_id", verified_ids).execute()

    # Delete the rooms themselves
    supabase.table("room").delete().in_("id", verified_ids).eq("pg_id", str(pg_id)).execute()

    return None

