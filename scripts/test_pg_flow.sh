#!/bin/bash
# Test script to verify the user-PG linkage flow
# Run: ./test_pg_flow.sh <YOUR_JWT_TOKEN>

TOKEN=$1

if [ -z "$TOKEN" ]; then
    echo "Usage: ./test_pg_flow.sh <YOUR_JWT_TOKEN>"
    exit 1
fi

echo "--- 1. Check current PG status (Should be 404 if no PG linked) ---"
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/pgs/me
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/pgs/me
echo -e "\n"

echo "--- 2. Create PG ---"
curl -s -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"name":"Test PG","address":"123 Test St"}' \
  http://localhost:8000/api/v1/pgs
echo -e "\n"

echo "--- 3. Verify Linkage (Should be 200 with PG Data) ---"
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/pgs/me
echo -e "\n"

echo "--- 4. Check Debug Endpoint ---"
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8000/api/v1/pgs/debug/user-pg-status
echo -e "\n"
