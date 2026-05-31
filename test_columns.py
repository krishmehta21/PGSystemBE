from db.supabase_client import supabase
try:
    res = supabase.table("tenant").select("*").limit(1).execute()
    if res.data:
        print("Success! Columns:", list(res.data[0].keys()))
    else:
        print("Success! No data, but query worked.")
except Exception as e:
    print("Error querying tenant:", e)
