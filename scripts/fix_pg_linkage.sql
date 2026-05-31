-- ========================================================================================
-- PG Control System - User-PG Linkage Fixes
-- This script fixes the missing relationships and RLS policies for creating a PG.
-- Run this in the Supabase SQL Editor.
-- ========================================================================================

-- 1. Ensure columns exist and relate correctly
-- The users table must have a pg_id column pointing to pg_property
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS pg_id UUID REFERENCES public.pg_property(id) ON DELETE SET NULL;

-- The pg_property table may optionally have an owner_id column pointing to users
-- We add this for extra data integrity, though auth flow currently updates users.pg_id
ALTER TABLE public.pg_property 
ADD COLUMN IF NOT EXISTS owner_id UUID REFERENCES public.users(id) ON DELETE CASCADE;

-- Default owner_id to auth.uid() on insert if possible, or application sets it.


-- 2. Fix Row Level Security (RLS) policies for `users` table
-- Ensure RLS is enabled
ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;

-- Allow users to UPDATE their own pg_id. 
-- IMPORTANT: Without this policy, linking a PG to a user silently fails and returns empty array.
DROP POLICY IF EXISTS "Users can update their own profile" ON public.users;
CREATE POLICY "Users can update their own profile" 
ON public.users 
FOR UPDATE 
TO authenticated 
USING (auth.uid() = id) 
WITH CHECK (auth.uid() = id);

-- Allow users to SELECT their own profile
DROP POLICY IF EXISTS "Users can read their own profile" ON public.users;
CREATE POLICY "Users can read their own profile" 
ON public.users 
FOR SELECT 
TO authenticated 
USING (auth.uid() = id);


-- 3. Fix Row Level Security (RLS) policies for `pg_property` table
ALTER TABLE public.pg_property ENABLE ROW LEVEL SECURITY;

-- Allow authenticated users to INSERT a new PG
DROP POLICY IF EXISTS "Authenticated users can create PG" ON public.pg_property;
CREATE POLICY "Authenticated users can create PG" 
ON public.pg_property 
FOR INSERT 
TO authenticated 
WITH CHECK (true); -- Anyone logged in can create a PG initially

-- Allow users to SELECT all PGs (or restrict if needed, but currently app lists them)
-- Alternatively, restrict to their own pg_id if they are an owner.
DROP POLICY IF EXISTS "User can view their PG" ON public.pg_property;
CREATE POLICY "User can view their PG" 
ON public.pg_property 
FOR SELECT 
TO authenticated 
USING (true); -- Allow read all for now, or change to restrict

-- Allow users to UPDATE the PG if they are the owner (either via owner_id or user's pg_id)
DROP POLICY IF EXISTS "Owner can update their PG" ON public.pg_property;
CREATE POLICY "Owner can update their PG" 
ON public.pg_property 
FOR UPDATE 
TO authenticated 
USING (
    owner_id = auth.uid() 
    OR 
    id IN (SELECT pg_id FROM public.users WHERE id = auth.uid())
) 
WITH CHECK (
    owner_id = auth.uid() 
    OR 
    id IN (SELECT pg_id FROM public.users WHERE id = auth.uid())
);

-- Allow users to DELETE their PG
DROP POLICY IF EXISTS "Owner can delete their PG" ON public.pg_property;
CREATE POLICY "Owner can delete their PG" 
ON public.pg_property 
FOR DELETE 
TO authenticated 
USING (
    owner_id = auth.uid() 
    OR 
    id IN (SELECT pg_id FROM public.users WHERE id = auth.uid())
);


-- ========================================================================================
-- DEBUG QUERIES (Run these to manually verify)
-- ========================================================================================

-- Verify schemas:
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'users';
-- SELECT column_name, data_type FROM information_schema.columns WHERE table_name = 'pg_property';

-- Verify RLS Policies:
-- SELECT * FROM pg_policies WHERE tablename IN ('users', 'pg_property');
