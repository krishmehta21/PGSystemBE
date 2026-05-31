from fastapi import APIRouter, HTTPException, status, Depends
from pydantic import BaseModel
from uuid import UUID
from db.supabase_client import supabase
from auth import get_current_user

router = APIRouter(prefix="/reminders", tags=["Reminders"], dependencies=[Depends(get_current_user)])

class ReminderCreate(BaseModel):
    tenant_id: UUID
    whatsapp_link: str

@router.post("/dispatch", status_code=status.HTTP_201_CREATED)
async def dispatch_reminder(
    payload: ReminderCreate,
    current_user: dict = Depends(get_current_user)
):
    pg_id = current_user.get("pg_id")
    if not pg_id:
        raise HTTPException(status_code=400, detail="No property linked to user")

    insert_data = {
        "pg_id": str(pg_id),
        "tenant_id": str(payload.tenant_id),
        "whatsapp_link": payload.whatsapp_link
    }

    try:
        response = supabase.table("rent_reminder_log").insert(insert_data).execute()
        if not response.data:
            raise HTTPException(status_code=500, detail="Failed to log rent reminder")
            
        return {"message": "Reminder logged successfully"}
    except Exception as e:
        print(f"Error logging reminder: {e}")
        raise HTTPException(status_code=500, detail=str(e))
