import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

sql = """
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'subscription_status_type') THEN
        CREATE TYPE subscription_status_type AS ENUM ('active', 'warning', 'suspended');
    END IF;
END $$;

ALTER TABLE pg_property 
  ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE,
  ADD COLUMN IF NOT EXISTS subscription_status subscription_status_type DEFAULT 'active';
"""

try:
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        print("Executing Subscription Paywall migration...")
        cur.execute(sql)
        print("Migration executed successfully!")
    conn.close()
except Exception as e:
    print("Error during migrations:", e)
