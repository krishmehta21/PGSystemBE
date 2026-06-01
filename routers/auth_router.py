from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel, EmailStr
from typing import Optional
from uuid import UUID

from db.supabase_client import supabase
from auth import hash_password, verify_password, create_access_token, get_current_user

router = APIRouter(prefix="/auth", tags=["Auth"])

class UserCreate(BaseModel):
    email: EmailStr
    password: str

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: UUID
    email: str
    pg_id: Optional[UUID] = None
    role: str = "owner"

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    pg_id: Optional[UUID] = None
    role: str = "owner"

class ActivationRequest(BaseModel):
    activation_code: str

@router.post("/google", response_model=TokenResponse)
async def google_login(payload: dict):
    supabase_token = payload.get("access_token")
    if not supabase_token:
        raise HTTPException(status_code=400, detail="Missing access_token")
        
    try:
        user_res = supabase.auth.get_user(supabase_token)
        if not user_res or not user_res.user:
            raise HTTPException(status_code=401, detail="Invalid token")
            
        user = user_res.user
        email = user.email
        
        existing_user = supabase.table("users").select("*").eq("email", email).execute()
        
        if existing_user.data and len(existing_user.data) > 0:
            db_user = existing_user.data[0]
        else:
            new_user_res = supabase.table("users").insert({
                "email": email,
                "role": "owner"
            }).execute()
            
            if not new_user_res.data:
                raise HTTPException(status_code=500, detail="Failed to create user record")
            db_user = new_user_res.data[0]
            
        if db_user.get("pg_id"):
            try:
                supabase.table("pg_activity_log").insert({
                    "pg_id": db_user["pg_id"],
                    "user_id": db_user["id"],
                    "event_type": "login"
                }).execute()
            except Exception as e:
                print(f"Activity logging failed: {e}")
                
        access_token = create_access_token(data={"sub": str(db_user["id"])})
        
        return {
            "access_token": access_token, 
            "token_type": "bearer", 
            "pg_id": db_user.get("pg_id"), 
            "role": db_user.get("role", "owner")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    try:
        # Check if user exists
        existing_user = supabase.table("users").select("id").eq("email", user_data.email).execute()
        if existing_user.data and len(existing_user.data) > 0:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Email already registered")

        # Hash the password
        try:
            hashed = hash_password(user_data.password)
        except Exception as e:
            print(f"Bcrypt Hashing Error: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Hashing error: {str(e)}")

        # Insert user
        try:
            new_user_res = supabase.table("users").insert({
                "email": user_data.email,
                "password_hash": hashed
            }).execute()
        except Exception as e:
            print(f"Supabase Insert Error: {str(e)}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Database error: {str(e)}")

        if not new_user_res.data:
            print(f"Supabase Insert failed (no data): {new_user_res}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to create user record")

        user = new_user_res.data[0]

        # Create token
        access_token = create_access_token(data={"sub": str(user["id"])})
        
        return {"access_token": access_token, "token_type": "bearer", "pg_id": user.get("pg_id"), "role": user.get("role", "owner")}
        
    except HTTPException:
        raise
    except Exception as e:
        print(f"UNEXPECTED ERROR in register: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))

@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    # Fetch user
    user_res = supabase.table("users").select("*").eq("email", user_data.email).execute()
    if not user_res.data or len(user_res.data) == 0:
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = user_res.data[0]

    # Verify password
    if not verify_password(user_data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    # Create token
    access_token = create_access_token(data={"sub": str(user["id"])})
    
    # Log activity
    if user.get("pg_id"):
        try:
            supabase.table("pg_activity_log").insert({
                "pg_id": user["pg_id"],
                "user_id": user["id"],
                "event_type": "login"
            }).execute()
        except Exception as e:
            print(f"Activity logging failed: {e}")
            
    return {"access_token": access_token, "token_type": "bearer", "pg_id": user.get("pg_id"), "role": user.get("role", "owner")}

@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "pg_id": current_user.get("pg_id"),
        "role": current_user.get("role", "owner")
    }

@router.post("/activate", response_model=UserResponse)
async def activate_pg(req: ActivationRequest, current_user: dict = Depends(get_current_user)):
    print(f"DEBUG: Activation attempt - User: {current_user.get('email')}, Code: {req.activation_code}")
    
    if current_user.get("pg_id"):
        raise HTTPException(status_code=400, detail="User is already linked to a property.")
        
    # Find PG by activation code
    pg_res = supabase.table("pg_property").select("*").eq("activation_code", req.activation_code).execute()
    
    if not pg_res.data:
        print(f"DEBUG: Code {req.activation_code} not found in pg_property")
        raise HTTPException(status_code=404, detail="Invalid activation code.")
        
    pg = pg_res.data[0]
    pg_id = pg["id"]
    print(f"DEBUG: Found PG {pg.get('name')} (ID: {pg_id})")
    
    # Update user with pg_id
    # CRITICAL: Use string ID for comparison
    user_id = str(current_user["id"])
    update_res = supabase.table("users").update({"pg_id": pg_id}).eq("id", user_id).execute()
    
    print(f"DEBUG: Update Result Data: {update_res.data}")
    
    if not update_res.data:
        # If data is empty, it means no rows were updated (likely RLS blocker)
        print(f"DEBUG: Update failed for User ID {user_id}. No rows affected.")
        raise HTTPException(
            status_code=500, 
            detail="Failed to link property. This is likely an RLS permission issue in the database. Please check policy: Users can update their own pg_id"
        )
        
    return {
        "id": current_user["id"],
        "email": current_user["email"],
        "pg_id": pg_id,
        "role": current_user.get("role", "owner")
    }
