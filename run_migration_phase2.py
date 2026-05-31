import os
import psycopg2
from dotenv import load_dotenv

# Load env variables from backend/.env
load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

sql = """
-- Phase 2 - Migration 3, 4, 5 & 6

-- 1. Create Maintenance Status ENUM safely
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'maintenance_status_enum') THEN
        CREATE TYPE maintenance_status_enum AS ENUM ('open', 'in_progress', 'resolved');
    END IF;
END $$;

-- 2. Create maintenance_request table
CREATE TABLE IF NOT EXISTS maintenance_request (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pg_id UUID NOT NULL REFERENCES pg_property(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    bed_id UUID REFERENCES bed(id) ON DELETE SET NULL,
    title VARCHAR(150) NOT NULL,
    description TEXT NOT NULL,
    status maintenance_status_enum DEFAULT 'open',
    created_at TIMESTAMPTZ DEFAULT now(),
    resolved_at TIMESTAMPTZ DEFAULT NULL
);

-- Enable RLS on maintenance_request
ALTER TABLE maintenance_request ENABLE ROW LEVEL SECURITY;

-- Create policy safely
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE policyname = 'Enable all actions for maintenance_requests' AND tablename = 'maintenance_request'
    ) THEN
        CREATE POLICY "Enable all actions for maintenance_requests" 
        ON maintenance_request FOR ALL 
        USING (true);
    END IF;
END $$;

-- Indexing for maintenance_request
CREATE INDEX IF NOT EXISTS idx_maintenance_pg_id ON maintenance_request(pg_id);
CREATE INDEX IF NOT EXISTS idx_maintenance_tenant_id ON maintenance_request(tenant_id);

-- 3. Alter tenant table to add soft-delete and move-out support
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT true;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS notice_given_date DATE DEFAULT NULL;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS actual_move_out_date DATE DEFAULT NULL;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS deposit_returned_amount NUMERIC(10,2) DEFAULT NULL;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS deposit_deduction_reason TEXT DEFAULT NULL;

-- Indexing tenant active status
CREATE INDEX IF NOT EXISTS idx_tenant_is_active ON tenant(is_active);

-- 4. Create rent_reminder_log table
CREATE TABLE IF NOT EXISTS rent_reminder_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pg_id UUID NOT NULL REFERENCES pg_property(id) ON DELETE CASCADE,
    tenant_id UUID NOT NULL REFERENCES tenant(id) ON DELETE CASCADE,
    whatsapp_link TEXT NOT NULL,
    sent_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE rent_reminder_log ENABLE ROW LEVEL SECURITY;

-- Create policy safely
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE policyname = 'Enable all for rent_reminder_logs' AND tablename = 'rent_reminder_log'
    ) THEN
        CREATE POLICY "Enable all for rent_reminder_logs" ON rent_reminder_log FOR ALL USING (true);
    END IF;
END $$;

-- Indexing for reminder log
CREATE INDEX IF NOT EXISTS idx_reminder_log_tenant_id ON rent_reminder_log(tenant_id);

-- 5. Expand Dashboard Stats RPC Function
CREATE OR REPLACE FUNCTION get_pg_dashboard(p_pg_id uuid)
RETURNS json AS $$
DECLARE
  v_pg_name VARCHAR;
  v_total_beds INT;
  v_occupied_beds INT;
  v_empty_beds INT;
  v_pending_payments INT;
  v_total_rent_collected NUMERIC;
  v_total_rent_expected NUMERIC;
  v_vacancy_rate NUMERIC;
  v_vacant_gt30_days_beds INT;
BEGIN
  -- Get PG Name
  SELECT name INTO v_pg_name FROM pg_property WHERE id = p_pg_id;

  -- Count beds
  SELECT COUNT(b.id) INTO v_total_beds 
  FROM room r 
  JOIN bed b ON b.room_id = r.id 
  WHERE r.pg_id = p_pg_id;

  -- Count occupied
  SELECT COUNT(b.id) INTO v_occupied_beds 
  FROM room r 
  JOIN bed b ON b.room_id = r.id 
  WHERE r.pg_id = p_pg_id AND b.is_occupied = true;

  -- Count empty
  v_empty_beds := v_total_beds - v_occupied_beds;

  -- Count pending payments (unpaid rent status for ACTIVE tenants)
  SELECT COUNT(t.id) INTO v_pending_payments 
  FROM room r 
  JOIN bed b ON b.room_id = r.id 
  JOIN tenant t ON t.bed_id = b.id
  WHERE r.pg_id = p_pg_id AND t.rent_status = 'unpaid' AND t.is_active = true;

  -- Total rent collected this month (paid status)
  SELECT COALESCE(SUM(t.rent_amount), 0) INTO v_total_rent_collected
  FROM room r 
  JOIN bed b ON b.room_id = r.id 
  JOIN tenant t ON t.bed_id = b.id
  WHERE r.pg_id = p_pg_id AND t.rent_status = 'paid' AND t.is_active = true;

  -- Total rent expected this month (total of all active tenants)
  SELECT COALESCE(SUM(t.rent_amount), 0) INTO v_total_rent_expected
  FROM room r 
  JOIN bed b ON b.room_id = r.id 
  JOIN tenant t ON t.bed_id = b.id
  WHERE r.pg_id = p_pg_id AND t.is_active = true;

  -- Vacancy rate calculation
  IF v_total_beds > 0 THEN
    v_vacancy_rate := ROUND((v_empty_beds::numeric / v_total_beds::numeric) * 100, 2);
  ELSE
    v_vacancy_rate := 0.00;
  END IF;

  -- Empty beds vacant for over 30 days
  SELECT COUNT(b.id) INTO v_vacant_gt30_days_beds
  FROM room r
  JOIN bed b ON b.room_id = r.id
  WHERE r.pg_id = p_pg_id 
    AND b.is_occupied = false 
    AND b.created_at < (now() - INTERVAL '30 days');

  RETURN json_build_object(
    'pg_name', COALESCE(v_pg_name, 'Unknown'),
    'total_beds', v_total_beds,
    'occupied_beds', v_occupied_beds,
    'empty_beds', v_empty_beds,
    'pending_payments', v_pending_payments,
    'total_rent_collected', v_total_rent_collected,
    'total_rent_expected', v_total_rent_expected,
    'vacancy_rate', v_vacancy_rate,
    'beds_vacant_gt30_days', v_vacant_gt30_days_beds
  );
END;
$$ LANGUAGE plpgsql STABLE;
"""

try:
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        print("Executing Phase 2 migrations...")
        cur.execute(sql)
        print("Migrations executed successfully!")
    conn.close()
except Exception as e:
    print("Error during migrations:", e)
