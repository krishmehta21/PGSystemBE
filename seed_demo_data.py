import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

OWNER_EMAIL = "krishmehta21@gmail.com"

# 20 rooms (Floor 1: 101-110, Floor 2: 201-210)
ROOM_NUMBERS = [
    "101", "102", "103", "104", "105", "106", "107", "108", "109", "110",
    "201", "202", "203", "204", "205", "206", "207", "208", "209", "210"
]
BED_LABELS = ["Bed 1", "Bed 2", "Bed 3"]

# 22 total demo phone numbers
DEMO_PHONES = [
    "9876542101", "9876542102", "9876542103", "9876542104", "9876542105",
    "9876542106", "9876542107", "9876542108", "9876542111", "9876542112",
    "9876542113", "9876542114", "9876542115", "9876542116", "9876542117",
    "9876542118", "9876542119", "9876542120", "9876542121", "9876542122",
    "9876542109", "9876542110"  # Inactive ones
]


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


def get_active_pg(cur):
    cur.execute(
        """
        SELECT u.id, u.email, u.pg_id, p.name
        FROM users u
        JOIN pg_property p ON p.id = u.pg_id
        WHERE lower(u.email) = lower(%s)
        """,
        (OWNER_EMAIL,),
    )
    row = cur.fetchone()
    if not row:
        raise RuntimeError(f"No active PG found for owner account {OWNER_EMAIL}")

    return {
        "user_id": row[0],
        "email": row[1],
        "pg_id": row[2],
        "pg_name": row[3],
    }


def clean_existing_demo_data(cur, pg_id):
    print("Cleaning up any existing demo records for DEMO_PHONES to ensure a fresh clean state...")
    
    # 1. Delete maintenance requests for demo tenants
    cur.execute(
        """
        DELETE FROM maintenance_request
        WHERE tenant_id IN (
            SELECT id FROM tenant WHERE phone = ANY(%s)
        )
        """,
        (DEMO_PHONES,),
    )
    
    # 2. Delete rent reminders for demo tenants
    cur.execute(
        """
        DELETE FROM rent_reminder_log
        WHERE tenant_id IN (
            SELECT id FROM tenant WHERE phone = ANY(%s)
        )
        """,
        (DEMO_PHONES,),
    )
    
    # 3. Free up any beds occupied by these demo tenants before deleting them
    cur.execute(
        """
        UPDATE bed
        SET is_occupied = false
        WHERE id IN (
            SELECT bed_id FROM tenant WHERE phone = ANY(%s) AND bed_id IS NOT NULL
        )
        """,
        (DEMO_PHONES,),
    )
    
    # 4. Delete demo tenants
    cur.execute(
        """
        DELETE FROM tenant
        WHERE phone = ANY(%s)
        """,
        (DEMO_PHONES,),
    )


def ensure_rooms_and_beds(cur, pg_id):
    created_rooms = []
    created_beds = []
    room_ids = {}

    for room_number in ROOM_NUMBERS:
        cur.execute(
            """
            SELECT id
            FROM room
            WHERE pg_id = %s AND room_number = %s
            ORDER BY created_at
            LIMIT 1
            """,
            (pg_id, room_number),
        )
        row = cur.fetchone()

        if row:
            room_id = row[0]
            cur.execute(
                "UPDATE room SET total_beds = %s WHERE id = %s",
                (len(BED_LABELS), room_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO room (pg_id, room_number, total_beds)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (pg_id, room_number, len(BED_LABELS)),
            )
            room_id = cur.fetchone()[0]
            created_rooms.append(room_number)

        room_ids[room_number] = room_id

        cur.execute(
            """
            SELECT bed_label
            FROM bed
            WHERE room_id = %s
            """,
            (room_id,),
        )
        existing_labels = {row[0] for row in cur.fetchall()}
        for label in BED_LABELS:
            if label in existing_labels:
                continue

            cur.execute(
                """
                INSERT INTO bed (room_id, bed_label, is_occupied)
                VALUES (%s, %s, false)
                RETURNING id
                """,
                (room_id, label),
            )
            cur.fetchone()
            created_beds.append(f"{room_number} {label}")

    # Fetch vacant beds for active tenants
    cur.execute(
        """
        SELECT b.id, r.room_number, b.bed_label
        FROM bed b
        JOIN room r ON r.id = b.room_id
        WHERE r.pg_id = %s
          AND r.room_number = ANY(%s)
          AND b.is_occupied = false
        ORDER BY r.room_number, b.bed_label
        """,
        (pg_id, ROOM_NUMBERS),
    )
    vacant_beds = cur.fetchall()

    return created_rooms, created_beds, vacant_beds


def tenant_rows(vacant_beds):
    today = date.today()
    
    # We need exactly 20 active tenants and 2 inactive tenants
    # Active specs: Name, Phone, Aadhaar, Rent, Deposit, Status, MoveIn, LastPaid, EmergencyName, EmergencyPhone, Employer, Hometown
    active_specs = [
        ("Aarav Sharma", "9876542101", "6421", 6500, 12000, "paid", months_ago(2), "2026-06-30", "Ramesh Sharma", "9812345670", "Infosys", "Jaipur"),
        ("Priya Nair", "9876542102", "1834", 7200, 15000, "unpaid", months_ago(8), "2026-06-08", "Meera Nair", "9823456710", "Manipal Hospital", "Kochi"),
        ("Rohan Gupta", "9876542103", "9072", 5800, 10000, "paid", months_ago(11), "2026-06-25", None, None, "TCS", "Lucknow"), # Lease renewal warning (11 months ago)
        ("Sneha Iyer", "9876542104", "4509", 8000, 15000, "unpaid", months_ago(2), "2026-06-12", "Anita Iyer", "9834567120", "Wipro", "Chennai"),
        ("Karan Malhotra", "9876542105", "7712", 6200, 10000, "paid", months_ago(8), "2026-06-28", None, None, "Zomato", "Delhi"),
        ("Neha Verma", "9876542106", "3198", 7000, 14000, "unpaid", months_ago(2), "2026-06-10", None, None, "Byju's", "Bhopal"),
        ("Vikram Rao", "9876542107", "5560", 5400, 8000, "paid", months_ago(8), "2026-06-27", None, None, "Swiggy", "Hyderabad"),
        ("Meera Kulkarni", "9876542108", "2245", 7600, 15000, "paid", months_ago(2), "2026-06-14", "Suresh Kulkarni", "9845671230", "Accenture", "Pune"),
        ("Aditya Joshi", "9876542111", "1029", 4800, 9000, "paid", months_ago(3), "2026-06-20", None, None, "Flipkart", "Ahmedabad"),
        ("Tanvi Bhat", "9876542112", "8821", 5200, 11000, "unpaid", months_ago(5), "2026-06-05", "Rajesh Bhat", "9856712344", "HCL", "Dehradun"),
        ("Arjun Reddy", "9876542113", "5534", 6800, 13000, "paid", months_ago(8), "2026-06-29", None, None, "Cognizant", "Bengaluru"),
        ("Ananya Das", "9876542114", "4412", 7500, 14000, "paid", months_ago(8), "2026-06-24", None, None, "Tech Mahindra", "Kolkata"),
        ("Kabir Mehta", "9876542115", "6678", 5000, 10000, "paid", months_ago(4), "2026-06-21", None, None, "Amazon", "Mumbai"),
        ("Diya Patel", "9876542116", "9901", 6100, 12000, "paid", months_ago(6), "2026-06-22", None, None, "Reliance", "Surat"),
        ("Rishi Choudhury", "9876542117", "2345", 4500, 8500, "paid", months_ago(2), "2026-06-18", None, None, "PwC", "Guwahati"),
        ("Ishita Saxena", "9876542118", "7890", 7100, 14000, "paid", months_ago(9), "2026-06-26", None, None, "Deloitte", "Patna"),
        ("Yash Wardhan", "9876542119", "3456", 5900, 12000, "paid", months_ago(8), "2026-06-23", None, None, "EY", "Kanpur"),
        ("Kavya Pillai", "9876542120", "8901", 6300, 13000, "paid", months_ago(3), "2026-06-19", "Mohan Pillai", "9890123456", "KPMG", "Trivandrum"),
        ("Devendra Singh", "9876542121", "4567", 5500, 10000, "paid", months_ago(4), "2026-06-15", None, None, "Tata Motors", "Chandigarh"),
        ("Shalini Mishra", "9876542122", "9012", 6700, 14000, "paid", months_ago(2), "2026-06-17", None, None, "L&T", "Ranchi"),
    ]

    tenants = []
    for index, spec in enumerate(active_specs):
        if index < len(vacant_beds):
            bed_id, room_number, bed_label = vacant_beds[index]
        else:
            # Fallback if somehow not enough beds, though 60 beds are ensured
            bed_id, room_number, bed_label = None, "Unknown", "Unknown"

        (
            name,
            phone,
            aadhaar,
            rent,
            deposit,
            rent_status,
            move_in,
            last_paid,
            emergency_name,
            emergency_phone,
            employer,
            hometown,
        ) = spec
        
        tenants.append(
            {
                "name": name,
                "phone": phone,
                "rent_amount": Decimal(rent),
                "bed_id": bed_id,
                "room": room_number,
                "bed_label": bed_label,
                "move_in_date": move_in,
                "rent_status": rent_status,
                "last_paid_date": date.fromisoformat(last_paid) if last_paid else None,
                "aadhaar_last4": aadhaar,
                "emergency_contact_name": emergency_name,
                "emergency_contact_phone": emergency_phone,
                "employer_or_college": employer,
                "hometown": hometown,
                "food_preference": "veg" if index % 2 == 0 else "both",
                "security_deposit_amount": Decimal(deposit),
                "security_deposit_date": move_in,
                "expected_move_out_date": today + timedelta(days=120 + index * 10),
                "police_verification_done": index % 3 != 0,
                "police_verification_date": move_in + timedelta(days=7),
                "occupancy_type": "single",
                "is_active": True,
            }
        )

    # 2 Inactive/moved-out tenants with full move-out records
    moved_out = [
        {
            "name": "Aditya Menon",
            "phone": "9876542109",
            "rent_amount": Decimal(6000),
            "bed_id": None,
            "move_in_date": months_ago(11),
            "rent_status": "paid",
            "last_paid_date": today - timedelta(days=38),
            "aadhaar_last4": "8871",
            "emergency_contact_name": "Lakshmi Menon",
            "emergency_contact_phone": "9856712340",
            "employer_or_college": "HDFC Bank",
            "hometown": "Mysuru",
            "food_preference": "veg",
            "security_deposit_amount": Decimal(10000),
            "security_deposit_date": months_ago(11),
            "expected_move_out_date": today - timedelta(days=7),
            "police_verification_done": True,
            "police_verification_date": months_ago(11) + timedelta(days=8),
            "occupancy_type": "single",
            "is_active": False,
            "notice_given_date": today - timedelta(days=35),
            "actual_move_out_date": today - timedelta(days=5),
            "deposit_returned_amount": Decimal(8500),
            "deposit_deduction_reason": "₹1,500 deducted for room repainting after move-out.",
        },
        {
            "name": "Pooja Bansal",
            "phone": "9876542110",
            "rent_amount": Decimal(6800),
            "bed_id": None,
            "move_in_date": months_ago(8),
            "rent_status": "paid",
            "last_paid_date": today - timedelta(days=46),
            "aadhaar_last4": "0933",
            "emergency_contact_name": None,
            "emergency_contact_phone": None,
            "employer_or_college": "Myntra",
            "hometown": "Indore",
            "food_preference": "non_veg",
            "security_deposit_amount": Decimal(12000),
            "security_deposit_date": months_ago(8),
            "expected_move_out_date": today - timedelta(days=14),
            "police_verification_done": True,
            "police_verification_date": months_ago(8) + timedelta(days=10),
            "occupancy_type": "single",
            "is_active": False,
            "notice_given_date": today - timedelta(days=42),
            "actual_move_out_date": today - timedelta(days=12),
            "deposit_returned_amount": Decimal(11000),
            "deposit_deduction_reason": "₹1,000 deducted for missing cupboard key replacement.",
        },
    ]

    return tenants + moved_out


def insert_tenants(cur, tenants):
    created = []
    sql = """
        INSERT INTO tenant (
            name, phone, rent_amount, bed_id, move_in_date, rent_status, last_paid_date,
            aadhaar_last4, emergency_contact_name, emergency_contact_phone,
            employer_or_college, hometown, food_preference, security_deposit_amount,
            security_deposit_date, expected_move_out_date, police_verification_done,
            police_verification_date, occupancy_type, is_active, notice_given_date,
            actual_move_out_date, deposit_returned_amount, deposit_deduction_reason
        )
        VALUES (
            %(name)s, %(phone)s, %(rent_amount)s, %(bed_id)s, %(move_in_date)s,
            %(rent_status)s, %(last_paid_date)s, %(aadhaar_last4)s,
            %(emergency_contact_name)s, %(emergency_contact_phone)s,
            %(employer_or_college)s, %(hometown)s, %(food_preference)s,
            %(security_deposit_amount)s, %(security_deposit_date)s,
            %(expected_move_out_date)s, %(police_verification_done)s,
            %(police_verification_date)s, %(occupancy_type)s, %(is_active)s,
            %(notice_given_date)s, %(actual_move_out_date)s,
            %(deposit_returned_amount)s, %(deposit_deduction_reason)s
        )
        RETURNING id, name, phone, is_active, rent_status, bed_id
    """
    for tenant in tenants:
        payload = {
            "notice_given_date": None,
            "actual_move_out_date": None,
            "deposit_returned_amount": None,
            "deposit_deduction_reason": None,
            **tenant,
        }
        cur.execute(sql, payload)
        row = cur.fetchone()
        created.append(
            {
                "id": row[0],
                "name": row[1],
                "phone": row[2],
                "is_active": row[3],
                "rent_status": row[4],
                "bed_id": row[5],
                "room": tenant.get("room"),
                "bed_label": tenant.get("bed_label"),
            }
        )
        if row[5]:
            cur.execute("UPDATE bed SET is_occupied = true WHERE id = %s", (row[5],))

    return created


def insert_maintenance(cur, pg_id, active_tenants):
    ticket_specs = [
        ("Broken AC", "AC in Room 101 is not cooling properly and needs service.", "open", 2),
        ("Water leakage", "Bathroom tap has a steady leak near the wash basin.", "open", 5),
        ("Faulty electrical socket", "Charging socket sparks intermittently and needs inspection.", "in_progress", 8),
        ("Door lock replacement", "Main door lock was replaced after key damage.", "resolved", 13),
    ]
    created = []
    now = datetime.now(timezone.utc)

    for index, (title, description, status, days_ago) in enumerate(ticket_specs):
        tenant = active_tenants[index]
        resolved_at = now - timedelta(days=2) if status == "resolved" else None
        cur.execute(
            """
            INSERT INTO maintenance_request (
                pg_id, tenant_id, bed_id, title, description, status, created_at, resolved_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING title, status
            """,
            (
                pg_id,
                tenant["id"],
                tenant["bed_id"],
                title,
                description,
                status,
                now - timedelta(days=days_ago),
                resolved_at,
            ),
        )
        row = cur.fetchone()
        created.append(f"{row[0]} ({row[1]})")

    return created


def insert_reminder_logs(cur, pg_id, unpaid_tenants):
    created = []
    now = datetime.now(timezone.utc)
    # 3 reminder logs with realistic timestamps from the past 2 weeks
    reminder_specs = [
        (unpaid_tenants[0], now - timedelta(days=12, hours=3)),
        (unpaid_tenants[1], now - timedelta(days=7, hours=5)),
        (unpaid_tenants[2], now - timedelta(days=2, hours=4)),
    ]

    for tenant, sent_at in reminder_specs:
        link = (
            "https://wa.me/91"
            f"{tenant['phone']}?text=Hi%20{tenant['name'].replace(' ', '%20')},"
            "%20your%20rent%20is%20pending.%20Please%20pay%20today."
        )
        cur.execute(
            """
            INSERT INTO rent_reminder_log (pg_id, tenant_id, whatsapp_link, sent_at)
            VALUES (%s, %s, %s, %s)
            RETURNING tenant_id, sent_at
            """,
            (pg_id, tenant["id"], link, sent_at),
        )
        cur.fetchone()
        created.append(f"{tenant['name']} reminder at {sent_at:%Y-%m-%d %H:%M UTC}")

    return created


def main():
    summary = {
        "rooms_created": [],
        "beds_created": [],
        "tenants_created": [],
        "maintenance_created": [],
        "reminders_created": [],
    }

    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    try:
        with conn:
            with conn.cursor() as cur:
                pg = get_active_pg(cur)
                print(f"Owner: {pg['email']}")
                print(f"Active PG: {pg['pg_name']} ({pg['pg_id']})")

                # Clean old demo data so we can seed the complete required dataset freshly
                clean_existing_demo_data(cur, pg["pg_id"])

                rooms_created, beds_created, vacant_beds = ensure_rooms_and_beds(cur, pg["pg_id"])
                summary["rooms_created"] = rooms_created
                summary["beds_created"] = beds_created

                tenants = tenant_rows(vacant_beds)
                created_tenants = insert_tenants(cur, tenants)
                summary["tenants_created"] = [
                    f"{t['name']} ({'active' if t['is_active'] else 'moved out'}, {t['rent_status']}, room {t['room'] or 'N/A'})"
                    for t in created_tenants
                ]

                active_tenants = [tenant for tenant in created_tenants if tenant["is_active"]]
                unpaid_tenants = [tenant for tenant in created_tenants if tenant["rent_status"] == "unpaid" and tenant["is_active"]]
                summary["maintenance_created"] = insert_maintenance(cur, pg["pg_id"], active_tenants)
                summary["reminders_created"] = insert_reminder_logs(cur, pg["pg_id"], unpaid_tenants)

        print("\nSeed completed successfully.")
        print("Summary:")
        print(f"- Rooms created: {len(summary['rooms_created'])} ({', '.join(summary['rooms_created']) or 'reused existing target rooms'})")
        print(f"- Beds created: {len(summary['beds_created'])} ({', '.join(summary['beds_created']) or 'all target beds already existed'})")
        print(f"- Tenants created: {len(summary['tenants_created'])}")
        for tenant in summary["tenants_created"]:
            print(f"  - {tenant}")
        print(f"- Maintenance tickets created: {len(summary['maintenance_created'])}")
        for ticket in summary["maintenance_created"]:
            print(f"  - {ticket}")
        print(f"- Rent reminder logs created: {len(summary['reminders_created'])}")
        for reminder in summary["reminders_created"]:
            print(f"  - {reminder}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
