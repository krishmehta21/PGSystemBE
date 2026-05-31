import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL is not set in .env")

sql = """
-- Phase 1 - Migration 1 & 2

-- Create ENUMs safely
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'food_preference_enum') THEN
        CREATE TYPE food_preference_enum AS ENUM ('veg', 'non_veg', 'both');
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'occupancy_type_enum') THEN
        CREATE TYPE occupancy_type_enum AS ENUM ('single', 'double', 'triple');
    END IF;
END $$;

-- Alter tenant table to add missing columns
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS aadhaar_last4 VARCHAR(4) CHECK (aadhaar_last4 ~ '^[0-9]{4}$' OR aadhaar_last4 IS NULL);
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS pan_number VARCHAR(10) CHECK (pan_number ~ '^[A-Z]{5}[0-9]{4}[A-Z]{1}$' OR pan_number IS NULL);
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS emergency_contact_name TEXT;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS emergency_contact_phone VARCHAR(15);
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS employer_or_college TEXT;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS hometown TEXT;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS food_preference food_preference_enum DEFAULT 'veg';
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS vehicle_registration TEXT;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS security_deposit_amount NUMERIC(10,2) DEFAULT NULL;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS security_deposit_date DATE DEFAULT NULL;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS expected_move_out_date DATE DEFAULT NULL;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS police_verification_done BOOLEAN DEFAULT false;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS police_verification_date DATE DEFAULT NULL;
ALTER TABLE tenant ADD COLUMN IF NOT EXISTS occupancy_type occupancy_type_enum DEFAULT 'single';

-- Create storage bucket for tenant documents
INSERT INTO storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
VALUES (
  'tenant-documents', 
  'tenant-documents', 
  false, 
  5242880, -- 5MB limit
  ARRAY['application/pdf', 'image/jpeg', 'image/png']
)
ON CONFLICT (id) DO NOTHING;

-- RLS policies for storage bucket access
DO $$ BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE policyname = 'Enable document uploads for authenticated users' AND tablename = 'objects' AND schemaname = 'storage'
    ) THEN
        CREATE POLICY "Enable document uploads for authenticated users" 
        ON storage.objects FOR INSERT 
        TO authenticated 
        WITH CHECK (bucket_id = 'tenant-documents');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE policyname = 'Enable document retrieval for authenticated users' AND tablename = 'objects' AND schemaname = 'storage'
    ) THEN
        CREATE POLICY "Enable document retrieval for authenticated users" 
        ON storage.objects FOR SELECT 
        TO authenticated 
        USING (bucket_id = 'tenant-documents');
    END IF;

    IF NOT EXISTS (
        SELECT 1 FROM pg_policies WHERE policyname = 'Enable document deletions for authenticated users' AND tablename = 'objects' AND schemaname = 'storage'
    ) THEN
        CREATE POLICY "Enable document deletions for authenticated users" 
        ON storage.objects FOR DELETE 
        TO authenticated 
        USING (bucket_id = 'tenant-documents');
    END IF;
END $$;
"""

try:
    print("Connecting to database...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    with conn.cursor() as cur:
        print("Executing migrations...")
        cur.execute(sql)
        print("Migrations executed successfully!")
    conn.close()
except Exception as e:
    print("Error during migrations:", e)
