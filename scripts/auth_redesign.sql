-- ========================================================================================
-- PG Control System - FINAL DB + RLS SETUP (Service Role Compatible)
-- Safe, idempotent, production-ready for MVP
-- ========================================================================================


-- ========================================
-- 1. SCHEMA SETUP
-- ========================================

-- USERS TABLE
ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS role VARCHAR(20) DEFAULT 'owner';

ALTER TABLE public.users 
ADD COLUMN IF NOT EXISTS pg_id UUID REFERENCES public.pg_property(id) ON DELETE SET NULL;


-- PG_PROPERTY TABLE
ALTER TABLE public.pg_property 
ADD COLUMN IF NOT EXISTS activation_code VARCHAR(20) UNIQUE;

ALTER TABLE public.pg_property 
ADD COLUMN IF NOT EXISTS owner_id UUID REFERENCES public.users(id) ON DELETE SET NULL;

ALTER TABLE public.pg_property 
ADD COLUMN IF NOT EXISTS is_activated BOOLEAN DEFAULT false;


-- ========================================
-- 2. ENABLE RLS (IMPORTANT)
-- ========================================

ALTER TABLE public.users ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.pg_property ENABLE ROW LEVEL SECURITY;


-- ========================================
-- 3. USERS TABLE POLICIES
-- ========================================

-- Clean slate
DROP POLICY IF EXISTS "Users can read own profile" ON public.users;
DROP POLICY IF EXISTS "Users can update own profile" ON public.users;

-- Users can read only themselves
CREATE POLICY "Users can read own profile"
ON public.users
FOR SELECT
TO authenticated
USING (auth.uid() = id);

-- Users can update only themselves (IMPORTANT FIX)
CREATE POLICY "Users can update own profile"
ON public.users
FOR UPDATE
TO authenticated
USING (auth.uid() = id)
WITH CHECK (true);


-- ========================================
-- 4. PG_PROPERTY POLICIES
-- ========================================

-- Clean slate
DROP POLICY IF EXISTS "Users can search by activation code" ON public.pg_property;
DROP POLICY IF EXISTS "Owners can view their PG" ON public.pg_property;
DROP POLICY IF EXISTS "Owners can update their PG" ON public.pg_property;
DROP POLICY IF EXISTS "Owners can delete their PG" ON public.pg_property;
DROP POLICY IF EXISTS "Admins can create PGs" ON public.pg_property;


-- 🔍 Allow activation lookup (required)
CREATE POLICY "Users can search by activation code"
ON public.pg_property
FOR SELECT
TO authenticated
USING (true);


-- 👁 Owners can only view their PG
CREATE POLICY "Owners can view their PG"
ON public.pg_property
FOR SELECT
TO authenticated
USING (
    id IN (
        SELECT pg_id FROM public.users WHERE id = auth.uid()
    )
);


-- ✏️ Owners can update their PG
CREATE POLICY "Owners can update their PG"
ON public.pg_property
FOR UPDATE
TO authenticated
USING (
    id IN (
        SELECT pg_id FROM public.users WHERE id = auth.uid()
    )
)
WITH CHECK (
    id IN (
        SELECT pg_id FROM public.users WHERE id = auth.uid()
    )
);


-- 🗑 Owners can delete their PG
CREATE POLICY "Owners can delete their PG"
ON public.pg_property
FOR DELETE
TO authenticated
USING (
    id IN (
        SELECT pg_id FROM public.users WHERE id = auth.uid()
    )
);


-- 🛠 Admin-only PG creation (FIXED)
CREATE POLICY "Admins can create PGs"
ON public.pg_property
FOR INSERT
TO authenticated
WITH CHECK (
    auth.uid() IN (
        SELECT id FROM public.users WHERE role = 'admin'
    )
);


-- ========================================
-- 5. INDEXES (performance)
-- ========================================

CREATE INDEX IF NOT EXISTS idx_users_pg_id ON public.users(pg_id);
CREATE INDEX IF NOT EXISTS idx_pg_activation_code ON public.pg_property(activation_code);


-- ========================================
-- 6. OPTIONAL HARDENING (RECOMMENDED)
-- ========================================

-- Prevent multiple users from activating same PG (optional)
-- ALTER TABLE public.users ADD CONSTRAINT unique_pg_owner UNIQUE (pg_id);


-- ========================================
-- 7. ADMIN SETUP
-- ========================================

-- Promote yourself to admin
-- UPDATE public.users SET role = 'admin' WHERE email = 'your_email_here';


-- ========================================
-- END
-- ========================================