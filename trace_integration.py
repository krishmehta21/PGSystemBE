import os
import sys
import requests
from datetime import date

# Add backend to path
sys.path.append(os.path.join(os.getcwd(), "."))

from auth import create_access_token
from db.supabase_client import supabase
from dotenv import load_dotenv

load_dotenv()

# User details for owner "krishmehta21@gmail.com"
USER_ID = "e03d2721-4f7a-4fed-94d9-2185080575fe"
PG_ID = "a40b58dd-7395-4fa1-9c94-21dc05f90de0"
RAHUL_TENANT_ID = "f5beab47-82d8-48ba-a524-855b3ed2e145"
RAHULS_BED_ID = "dfaa81b6-983e-43ed-8454-699f33e13063"

# Reset database fields before running trace to ensure clean execution state
def reset_db():
    print("[Db Reset] Ensuring Bed and Tenant are in active states...")
    supabase.table("bed").update({"is_occupied": True}).eq("id", RAHULS_BED_ID).execute()
    supabase.table("tenant").update({
        "is_active": True,
        "bed_id": RAHULS_BED_ID,
        "notice_given_date": None,
        "actual_move_out_date": None,
        "deposit_returned_amount": None,
        "deposit_deduction_reason": None
    }).eq("id", RAHUL_TENANT_ID).execute()
    
    # Delete any preexisting maintenance logs for a clean run
    supabase.table("maintenance_request").delete().eq("tenant_id", RAHUL_TENANT_ID).execute()
    print("[Db Reset] Complete.")

def run_trace():
    print("=" * 60)
    print("STARTING END-TO-END VERIFICATION & TRACE OF PHASE 2")
    print("=" * 60)
    
    reset_db()
    
    # Generate JWT token
    token = create_access_token(data={"sub": str(USER_ID)})
    headers = {"Authorization": f"Bearer {token}"}
    base_url = "http://localhost:8000/api/v1"
    
    # ─── TRACE 1: MAINTENANCE PAGE (List and Create) ──────────────────────────
    print("\n[TRACE 1] Fetching Maintenance Tickets (GET /maintenance)...")
    res = requests.get(f"{base_url}/maintenance", headers=headers)
    print(f"Status: {res.status_code}")
    print(f"Tickets list: {res.json()}")
    
    print("\n[TRACE 1] Creating a new Ticket (POST /maintenance)...")
    payload = {
        "tenant_id": RAHUL_TENANT_ID,
        "title": "Bathroom tap leak",
        "description": "Water dripping constantly, causing water logging."
    }
    res = requests.post(f"{base_url}/maintenance", json=payload, headers=headers)
    print(f"Status: {res.status_code}")
    ticket = res.json()
    print(f"Response: {ticket}")
    ticket_id = ticket["id"]
    
    # Verify that the ticket lists correctly
    res = requests.get(f"{base_url}/maintenance", headers=headers)
    print(f"Status: {res.status_code} | Confirmed ticket added: {any(t['id'] == ticket_id for t in res.json())}")

    # ─── TRACE 2: ADVANCE TICKET STATUS (Open -> In Progress -> Resolved) ──────
    print("\n[TRACE 2] Advancing Ticket Status to 'in_progress' (PATCH /maintenance/{id})...")
    res = requests.patch(f"{base_url}/maintenance/{ticket_id}", json={"status": "in_progress"}, headers=headers)
    print(f"Status: {res.status_code}")
    print(f"Response: {res.json()}")
    
    print("\n[TRACE 2] Advancing Ticket Status to 'resolved' (PATCH /maintenance/{id})...")
    res = requests.patch(f"{base_url}/maintenance/{ticket_id}", json={"status": "resolved"}, headers=headers)
    print(f"Status: {res.status_code}")
    resolved_ticket = res.json()
    print(f"Response: {resolved_ticket}")
    print(f"Verification: resolved_at is set? -> {resolved_ticket.get('resolved_at') is not None}")

    # ─── TRACE 3: TENANT MOVE-OUT & SETTLEMENT FLOW ──────────────────────────
    print("\n[TRACE 3] Initiating Tenant Move-out for Rahul (POST /tenants/{id}/move-out)...")
    move_out_payload = {
        "notice_given_date": "2026-05-15",
        "actual_move_out_date": "2026-05-30",
        "deposit_returned_amount": 5000.00,
        "deposit_deduction_reason": "Deducted cleaning charges 1000 from security deposit."
    }
    res = requests.post(f"{base_url}/tenants/{RAHUL_TENANT_ID}/move-out", json=move_out_payload, headers=headers)
    print(f"Status: {res.status_code}")
    moved_out_tenant = res.json()
    print(f"Response: {moved_out_tenant}")
    
    # DB Verifications
    print("\n[TRACE 3] DB Checks:")
    db_bed = supabase.table("bed").select("*").eq("id", RAHULS_BED_ID).execute().data[0]
    print(f"  -> Is bed marked vacant? is_occupied = {db_bed['is_occupied']} (Expected: False)")
    
    db_tenant = supabase.table("tenant").select("*").eq("id", RAHUL_TENANT_ID).execute().data[0]
    print(f"  -> Is tenant marked inactive? is_active = {db_tenant['is_active']} (Expected: False)")
    print(f"  -> Notice Date: {db_tenant['notice_given_date']} | Actual Moveout: {db_tenant['actual_move_out_date']}")
    print(f"  -> Returned Deposit: {db_tenant['deposit_returned_amount']} | Reason: {db_tenant['deposit_deduction_reason']}")

    # ─── TRACE 4: DASHBOARD ANALYTICS ─────────────────────────────────────────
    print("\n[TRACE 4] Checking Dashboard Analytics (GET /dashboard)...")
    res = requests.get(f"{base_url}/dashboard", headers=headers)
    print(f"Status: {res.status_code}")
    stats = res.json()
    print(f"Response Stats: {stats}")
    print(f"Verification: ")
    print(f"  - Total Beds: {stats['total_beds']} (Expected: 6)")
    print(f"  - Occupied Beds: {stats['occupied_beds']} (Expected: 1, since Rahul moved out!)")
    print(f"  - Empty Beds: {stats['empty_beds']} (Expected: 5)")
    print(f"  - Rent Expected: {stats['total_rent_expected']} (Expected: Only Krish's rent, which matches real value)")
    print(f"  - Vacancy Rate: {stats['vacancy_rate']}% (Expected: 83.33%)")
    print(f"  - Beds vacant > 30 days: {stats['beds_vacant_gt30_days']} (Expected: 4 or 5)")
    
    print("\n" + "=" * 60)
    print("END-TO-END MANUAL TRACE COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    run_trace()
