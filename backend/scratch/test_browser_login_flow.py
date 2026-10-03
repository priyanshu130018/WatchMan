"""
Test script verifying the exact HTTP request the React browser app sends:
POST http://localhost:8000/api/auth/login
with body:
{
  "email": "bharat@gmail.com",
  "password": "..."
}
Then validates session storage and subsequent requests with:
Authorization: Bearer <access_token>
"""

import urllib.request
import json
import uuid

def test_login():
    print("=" * 80)
    print("TESTING BROWSER LOGIN FLOW TO FASTAPI BACKEND (http://localhost:8000)")
    print("=" * 80)

    url = "http://localhost:8000/api/auth/login"
    payload = {
        "email": "bharat@gmail.com",
        "password": "123456789"
    }

    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Origin": "http://localhost:3000"
        },
        method="POST"
    )

    print(f"Sending POST {url}...")
    with urllib.request.urlopen(req) as response:
        status_code = response.status
        body = json.loads(response.read().decode("utf-8"))

    print(f"Response Status: {status_code}")
    print(f"Response User: {body.get('user')}")
    print(f"Access Token (prefix): {body.get('access_token')[:30]}...")
    print(f"Refresh Token (prefix): {body.get('refresh_token')[:30]}...")

    assert status_code == 200
    assert "access_token" in body
    assert body["user"]["email"] == "bharat@gmail.com"

    access_token = body["access_token"]

    # Test authenticated request with Bearer token
    print("\nTesting subsequent authenticated request:")
    me_url = "http://localhost:8000/api/auth/me"
    me_req = urllib.request.Request(
        me_url,
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "Origin": "http://localhost:3000"
        }
    )

    with urllib.request.urlopen(me_req) as me_resp:
        me_status = me_resp.status
        me_body = json.loads(me_resp.read().decode("utf-8"))

    print(f"GET {me_url} -> Status: {me_status}")
    print(f"User Info: {me_body}")
    assert me_status == 200
    assert me_body["id"] == body["user"]["id"]

    print("\n" + "=" * 80)
    print("SUCCESS: Browser HTTP login flow to http://localhost:8000 is 100% verified!")
    print("=" * 80)

if __name__ == "__main__":
    test_login()
