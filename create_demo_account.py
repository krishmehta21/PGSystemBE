import os
import random
import string
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import psycopg2
from dotenv import load_dotenv

import bcrypt

def hash_password(password: str) -> str:
    pwd_bytes = password.encode('utf-8')
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(pwd_bytes, salt)
    return hashed.decode('utf-8')

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

DEMO_EMAIL = "demo@rentflow.in"
DEMO_PASSWORD = "Demo@1234"
PG_NAME = "Sunrise PG"
PG_ADDRESS = "14th Cross, Sector 6, HSR Layout, Bengaluru"

ROOMS_FLOOR_1 = [
    ("101", 3), ("102", 3), ("103", 2), ("104", 3), ("105", 2)
]
ROOMS_FLOOR_2 = [
    ("201", 3), ("202", 3), ("203", 2), ("204", 3)
]

ALL_ROOMS = ROOMS_FLOOR_1 + ROOMS_FLOOR_2

def generate_activation_code(length=6):
    return ''.join(random.choices(string.ascii_uppercase + string.digits, k=length))

def months_ago(months: int) -> date:
    today = date.today()
    month = today.month - months
    year = today.year
    while month <= 0:
        month += 12
        year -= 1

    max_day = 28
    if month in {1, 3, 5, 7, 8, 10, 12}:
        max_day = 31
    elif month in {4, 6, 9, 11}:
        max_day = 30
    elif year % 4 == 0 and (year % 100 != 0 or year % 400 == 0):
        max_day = 29

    return date(year, month, min(today.day, max_day))

def get_or_create_user(cur):
    cur.execute("SELECT id, pg_id FROM users WHERE email = %s", (DEMO_EMAIL,))
    row = cur.fetchone()
    if row:
        print("Demo user already exists.")
        return row[0], row[1]
    
    print("Creating demo user...")
    hashed = hash_password(DEMO_PASSWORD)
    cur.execute(
        """
        INSERT INTO users (email, password_hash, role)
        VALUES (%s, %s, 'owner')
        RETURNING id
        """,
        (DEMO_EMAIL, hashed)
    )
    user_id = cur.fetchone()[0]
    return user_id, None

def get_or_create_pg(cur, user_id, existing_pg_id):
    if existing_pg_id:
        cur.execute("SELECT id, activation_code FROM pg_property WHERE id = %s", (existing_pg_id,))
        row = cur.fetchone()
        if row:
            print("Demo PG already exists.")
            return row[0], row[1]
            
    cur.execute("SELECT id, activation_code FROM pg_property WHERE owner_id = %s LIMIT 1", (user_id,))
    row = cur.fetchone()
    if row:
        print("Demo PG already exists.")
        # Update user's pg_id
        cur.execute("UPDATE users SET pg_id = %s WHERE id = %s", (row[0], user_id))
        return row[0], row[1]

    print("Creating demo PG property...")
    activation_code = generate_activation_code()
    cur.execute(
        """
        INSERT INTO pg_property (name, address, activation_code, owner_id, is_active, subscription_status)
        VALUES (%s, %s, %s, %s, true, 'active')
        RETURNING id
        """,
        (PG_NAME, PG_ADDRESS, activation_code, user_id)
    )
    pg_id = cur.fetchone()[0]
    
    cur.execute("UPDATE users SET pg_id = %s WHERE id = %s", (pg_id, user_id))
    return pg_id, activation_code

def setup_rooms_and_beds(cur, pg_id):
    print("Setting up rooms and beds...")
    room_map = {}
    bed_map = {} # room_number -> [bed_ids]
    
    # Clean existing for idempotency
    cur.execute("DELETE FROM room WHERE pg_id = %s", (pg_id,))
    
    for room_number, num_beds in ALL_ROOMS:
        cur.execute(
            """
            INSERT INTO room (pg_id, room_number, total_beds)
            VALUES (%s, %s, %s)
            RETURNING id
            """,
            (pg_id, room_number, num_beds)
        )
        room_id = cur.fetchone()[0]
        room_map[room_number] = room_id
        bed_map[room_number] = []
        
        for i in range(1, num_beds + 1):
            cur.execute(
                """
                INSERT INTO bed (room_id, bed_label, is_occupied)
                VALUES (%s, %s, false)
                RETURNING id
                """,
                (room_id, f"Bed {i}")
            )
            bed_map[room_number].append(cur.fetchone()[0])
            
    return room_map, bed_map

def setup_tenants(cur, pg_id, bed_map):
    print("Setting up tenants...")
    today = date.today()
    
    tenants_data = [
        ("Aarav Sharma", "101", 1, 7500, "paid", months_ago(8)),
        ("Priya Nair", "101", 2, 7500, "unpaid", months_ago(3)),
        ("Rohan Gupta", "101", 3, 7500, "paid", months_ago(11)),
        ("Sneha Iyer", "102", 1, 8000, "unpaid", months_ago(2)),
        ("Karan Malhotra", "102", 2, 8000, "paid", months_ago(5)),
        ("Neha Verma", "102", 3, 8000, "unpaid", months_ago(1)),
        ("Vikram Rao", "103", 1, 6500, "paid", months_ago(6)),
        ("Meera Kulkarni", "103", 2, 6500, "paid", months_ago(4)),
        ("Aditya Joshi", "104", 1, 7000, "unpaid", months_ago(2)),
        ("Tanvi Bhat", "104", 2, 7000, "paid", months_ago(7)),
        ("Rahul Desai", "104", 3, 7000, "paid", months_ago(9)),
        ("Ananya Singh", "105", 1, 6000, "unpaid", months_ago(3)),
        ("Suresh Pillai", "201", 1, 8500, "paid", months_ago(5)),
        ("Divya Menon", "201", 2, 8500, "paid", months_ago(2)),
        ("Arjun Nambiar", "202", 1, 8500, "unpaid", months_ago(1)),
        ("Kavya Reddy", "202", 2, 8500, "paid", months_ago(4)),
    ]
    
    base_phone = 9876000000
    created_tenants = {}
    
    for i, t in enumerate(tenants_data):
        name, room_num, bed_idx, rent, status, move_in = t
        phone = str(base_phone + i)
        aadhaar = str(random.randint(1000, 9999))
        bed_id = bed_map[room_num][bed_idx - 1]
        deposit = rent * 2
        food = "veg" if i % 2 == 0 else "non_veg"
        
        cur.execute(
            """
            INSERT INTO tenant (
                name, phone, rent_amount, bed_id, move_in_date, rent_status, last_paid_date,
                aadhaar_last4, food_preference, security_deposit_amount, security_deposit_date,
                expected_move_out_date, police_verification_done, occupancy_type, is_active
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, true, 'single', true
            ) RETURNING id
            """,
            (
                name, phone, rent, bed_id, move_in, status, 
                today - timedelta(days=5) if status == 'paid' else None,
                aadhaar, food, deposit, move_in,
                today + timedelta(days=180),
            )
        )
        tenant_id = cur.fetchone()[0]
        created_tenants[name] = tenant_id
        
        cur.execute("UPDATE bed SET is_occupied = true WHERE id = %s", (bed_id,))
        
    return created_tenants

def setup_moved_out_tenant(cur):
    print("Setting up moved-out tenant...")
    today = date.today()
    cur.execute(
        """
        INSERT INTO tenant (
            name, phone, rent_amount, move_in_date, rent_status,
            aadhaar_last4, food_preference, security_deposit_amount, security_deposit_date,
            occupancy_type, is_active, notice_given_date, actual_move_out_date,
            deposit_returned_amount, deposit_deduction_reason
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, 'single', false, %s, %s, %s, %s
        )
        """,
        (
            "Sanjay Kumar", "9876500999", 6500, months_ago(8), "paid",
            "1234", "veg", 13000, months_ago(8),
            today - timedelta(days=90), months_ago(2), 13000,
            "Minor wall scuff repair"
        )
    )

def setup_maintenance_tickets(cur, pg_id, created_tenants, bed_map):
    print("Setting up maintenance tickets...")
    now = datetime.now(timezone.utc)
    
    tickets = [
        ("Broken geyser", "open", "Sneha Iyer", "102", 1, None),
        ("Leaking tap in bathroom", "open", "Suresh Pillai", "201", 1, None),
        ("Faulty electrical socket", "in_progress", "Aditya Joshi", "104", 1, None),
        ("Door lock replacement", "resolved", "Aarav Sharma", "101", 1, now - timedelta(days=5)),
    ]
    
    for title, status, t_name, room, bed_idx, resolved in tickets:
        t_id = created_tenants[t_name]
        b_id = bed_map[room][bed_idx - 1]
        
        cur.execute(
            """
            INSERT INTO maintenance_request (
                pg_id, tenant_id, bed_id, title, description, status, created_at, resolved_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (pg_id, t_id, b_id, title, "Demo description", status, now - timedelta(days=10), resolved)
        )

def setup_reminders(cur, pg_id, created_tenants):
    print("Setting up reminders...")
    now = datetime.now(timezone.utc)
    targets = [("Priya Nair", 2), ("Sneha Iyer", 5), ("Ananya Singh", 8)]
    
    for t_name, days_ago in targets:
        t_id = created_tenants[t_name]
        cur.execute(
            """
            INSERT INTO rent_reminder_log (pg_id, tenant_id, whatsapp_link, sent_at)
            VALUES (%s, %s, 'https://wa.me/demo', %s)
            """,
            (pg_id, t_id, now - timedelta(days=days_ago))
        )

def main():
    print("Connecting to DB...")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                user_id, pg_id_existing = get_or_create_user(cur)
                pg_id, activation_code = get_or_create_pg(cur, user_id, pg_id_existing)
                
                # Check if we already seeded tenants for this PG to ensure idempotency
                cur.execute("SELECT count(*) FROM tenant WHERE phone LIKE '98760000%%'")
                if cur.fetchone()[0] == 0:
                    room_map, bed_map = setup_rooms_and_beds(cur, pg_id)
                    created_tenants = setup_tenants(cur, pg_id, bed_map)
                    setup_moved_out_tenant(cur)
                    setup_maintenance_tickets(cur, pg_id, created_tenants, bed_map)
                    setup_reminders(cur, pg_id, created_tenants)
                else:
                    print("Data already seeded.")
                    
        print("\n====== DEMO ACCOUNT CREATED ======")
        print("URL:      https://pg-system-fe.vercel.app")
        print(f"Email:    {DEMO_EMAIL}")
        print(f"Password: {DEMO_PASSWORD}")
        print(f"PG Name:  {PG_NAME}")
        print("Rooms:    9 | Beds: 24 | Tenants: 16 | Vacant: 8")
        print(f"Activation Key: {activation_code}")
        print("==================================")
    finally:
        conn.close()

if __name__ == "__main__":
    main()
