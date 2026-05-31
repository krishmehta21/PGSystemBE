from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from uuid import UUID
from db.supabase_client import supabase
from routers import rooms, beds, tenants, rent, pg, auth_router, maintenance, reminders
from models.schemas import DashboardResponse
from dotenv import load_dotenv
from auth import get_current_user
from typing import Optional
from uuid import UUID
from fastapi.responses import JSONResponse
from fastapi import Request
import traceback
import os
from utils import serialize_decimals
load_dotenv()

app = FastAPI(title="PG Control System API", version="1.0.0")

# CORS Middleware
origins = [
    "https://pg-system-fe.vercel.app",
    "http://localhost:5173",
    "http://localhost:3000",
]

frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
if frontend_url not in origins:
    origins.append(frontend_url)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    print(f"GLOBAL ERROR: {type(exc).__name__}: {str(exc)}")
    traceback.print_exc()
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal Server Error: {str(exc)}"},
    )


# Ping endpoint
@app.get("/ping", tags=["System"])
async def ping_check():
    return {"status": "ok", "version": "1.0.0"}

# Dashboard endpoint
@app.get("/api/v1/dashboard", response_model=DashboardResponse, tags=["Dashboard"])
async def get_dashboard(pg_id: Optional[UUID] = None, current_user: dict = Depends(get_current_user)):
    try:
        if pg_id and current_user.get("role") == "admin":
            effective_pg_id = pg_id
        else:
            # Strictly use current_user's pg_id
            effective_pg_id = current_user.get("pg_id")
        
        if not effective_pg_id:
            return {
                "pg_name": "Setup Pending",
                "total_beds": 0,
                "occupied_beds": 0,
                "empty_beds": 0,
                "pending_payments": 0
            }

        # Use the RPC function defined in seed.sql
        response = supabase.rpc("get_pg_dashboard", {"p_pg_id": str(effective_pg_id)}).execute()
        
        if hasattr(response, 'error') and response.error:
            print(f"Supabase RPC Error: {response.error}")
            return {
                "pg_name": "PG Linked",
                "total_beds": 0,
                "occupied_beds": 0,
                "empty_beds": 0,
                "pending_payments": 0
            }
            
        if not response.data:
            # Maybe the PG was deleted or ID is stale
            return {
                "pg_name": "Property Not Found",
                "total_beds": 0,
                "occupied_beds": 0,
                "empty_beds": 0,
                "pending_payments": 0
            }
            
        return serialize_decimals(response.data)
    except Exception as e:
        print(f"Dashboard Endpoint Error: {str(e)}")
        return {
            "pg_name": "Unavailable",
            "total_beds": 0,
            "occupied_beds": 0,
            "empty_beds": 0,
            "pending_payments": 0
        }


# Include Routers
app.include_router(auth_router.router, prefix="/api/v1")
app.include_router(pg.router, prefix="/api/v1")
app.include_router(rooms.router, prefix="/api/v1")
app.include_router(beds.router, prefix="/api/v1")
app.include_router(rent.router, prefix="/api/v1")  # BEFORE tenants to catch /unpaid
app.include_router(tenants.router, prefix="/api/v1")
app.include_router(maintenance.router, prefix="/api/v1")
app.include_router(reminders.router, prefix="/api/v1")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
