-- Table: pg_property
CREATE TABLE pg_property (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    address TEXT,
    whatsapp_message_template TEXT DEFAULT 'Hi {name}, your rent of ₹{amount} for this month is pending. Please pay today. — {pgName}',
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Table: room
CREATE TABLE room (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pg_id UUID NOT NULL REFERENCES pg_property(id) ON DELETE CASCADE,
    room_number VARCHAR(20) NOT NULL,
    total_beds INTEGER NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Table: bed
CREATE TABLE bed (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    room_id UUID NOT NULL REFERENCES room(id) ON DELETE CASCADE,
    bed_label VARCHAR(20),
    is_occupied BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Table: tenant
CREATE TABLE tenant (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(100) NOT NULL,
    phone VARCHAR(15) NOT NULL,
    rent_amount NUMERIC(10,2) NOT NULL,
    bed_id UUID UNIQUE REFERENCES bed(id) ON DELETE SET NULL,
    move_in_date DATE NOT NULL,
    rent_status TEXT CHECK (rent_status IN ('paid', 'unpaid')) DEFAULT 'unpaid',
    last_paid_date DATE,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Table: users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email VARCHAR(255) UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    pg_id UUID REFERENCES pg_property(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Enable RLS
ALTER TABLE pg_property ENABLE ROW LEVEL SECURITY;
ALTER TABLE room ENABLE ROW LEVEL SECURITY;
ALTER TABLE bed ENABLE ROW LEVEL SECURITY;
ALTER TABLE tenant ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;

-- users Policies
CREATE POLICY "Enable insert for registration" ON users FOR INSERT WITH CHECK (true);
CREATE POLICY "Enable select for login/me" ON users FOR SELECT USING (true);
CREATE POLICY "Enable update for linking pg" ON users FOR UPDATE USING (true);

-- pg_property Policies
CREATE POLICY "Enable all for pgs" ON pg_property FOR ALL USING (true);

-- room Policies
CREATE POLICY "Enable all for rooms" ON room FOR ALL USING (true);

-- bed Policies
CREATE POLICY "Enable all for beds" ON bed FOR ALL USING (true);

-- tenant Policies
CREATE POLICY "Enable all for tenants" ON tenant FOR ALL USING (true);

-- Add Indexes
CREATE INDEX idx_tenant_bed_id ON tenant(bed_id);
CREATE INDEX idx_bed_room_id ON bed(room_id);
CREATE INDEX idx_room_pg_id ON room(pg_id);

-- Dashboard RPC Function
CREATE OR REPLACE FUNCTION get_pg_dashboard(p_pg_id uuid)
RETURNS json AS $$
  SELECT json_build_object(
    'pg_name', p.name,
    'total_beds', COUNT(b.id),
    'occupied_beds', COUNT(b.id) FILTER (WHERE b.is_occupied = true),
    'empty_beds', COUNT(b.id) FILTER (WHERE b.is_occupied = false),
    'pending_payments', COUNT(t.id) FILTER (WHERE t.rent_status = 'unpaid')
  )
  FROM pg_property p
  LEFT JOIN room r ON r.pg_id = p.id
  LEFT JOIN bed b ON b.room_id = r.id
  LEFT JOIN tenant t ON t.bed_id = b.id
  WHERE p.id = p_pg_id
  GROUP BY p.name;
$$ LANGUAGE sql STABLE;
