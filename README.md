# PG Control System Backend

FastAPI-based backend for the PG Control System, using Supabase as the database.

## Prerequisites
- Python 3.9+
- Supabase account and project

## Setup Instructions

1. **Install Dependencies**
   ```bash
   cd backend
   pip install -r requirements.txt
   ```

2. **Configure Environment Variables**
   - Copy `.env.example` to `.env`:
     ```bash
     cp .env.example .env
     ```
   - Fill in your `SUPABASE_URL` and `SUPABASE_KEY` (anon key) from your Supabase project settings.

3. **Database Setup**
   - Open the Supabase SQL Editor in your dashboard.
   - Copy the contents of `db/seed.sql` and run it to create the tables, indexes, and the dashboard RPC function.

4. **Run the Development Server**
   ```bash
   uvicorn main:app --reload
   ```
   The API will be available at `http://localhost:8000`.
   Swagger documentation is at `http://localhost:8000/docs`.

## API Endpoints

### Dashboard
- `GET /api/v1/dashboard?pg_id={uuid}`: Summary statistics for the PG.

### Rooms
- `GET /api/v1/rooms?pg_id={uuid}`: List all rooms.
- `POST /api/v1/rooms`: Create a room (auto-creates beds).
- `PUT /api/v1/rooms/{id}`: Update room details.
- `DELETE /api/v1/rooms/{id}`: Delete a room.

### Beds
- `GET /api/v1/beds?room_id={uuid}`: List beds for a room.

### Tenants
- `GET /api/v1/tenants?pg_id={uuid}`: List all tenants with room/bed info.
- `GET /api/v1/tenants/{id}`: Get specific tenant details.
- `POST /api/v1/tenants`: Create/assign a tenant (marks bed occupied).
- `DELETE /api/v1/tenants/{id}`: Remove a tenant (marks bed empty).

### Rent
- `PATCH /api/v1/tenants/{id}/rent`: Toggle rent status (`paid`/`unpaid`).
- `GET /api/v1/tenants/unpaid?pg_id={uuid}`: List tenants with pending rent.

## Frontend Connection
Set `VITE_API_URL=http://localhost:8000/api/v1` in your frontend configuration.

## System
- `GET /health`: Basic health check.
