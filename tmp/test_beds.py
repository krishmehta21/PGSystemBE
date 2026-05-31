import requests
import uuid

BASE_URL = "http://localhost:8000/api/v1"

# Note: We need a valid token to test authenticated endpoints.
# However, since this is a local dev environment, I might not have one easily.
# I'll check if there's a way to get a token or if I can skip auth for a moment.
# Looking at the code, get_current_user is required.

def test_beds():
    # This is a placeholder for manual verification steps
    # In a real scenario, I'd get a token first.
    print("Manual verification steps:")
    print("1. POST /api/v1/beds with room_id")
    print("2. PUT /api/v1/beds/{id} with bed_label")
    print("3. DELETE /api/v1/beds/{id}")
    print("4. DELETE /api/v1/beds/{id} (where is_occupied=True) -> 400")

if __name__ == "__main__":
    test_beds()
