import requests

def verify_logins():
    test_users = [
        'aryan@gmail.com',
        'bharat@gmail.com',
        'aman@gmail.com',
        'saket@gmail.com',
        'priyanshu@gmail.com',
        'neha@gmail.com',
        'priya@gmail.com',
        'sakshi@gmail.com',
        'sid@gmail.com',
        'aditya@gmail.com'
    ]

    print("=== TESTING API LOGIN ENDPOINT (POST /api/auth/login) FOR ALL 10 USERS ===")
    all_success = True
    for email in test_users:
        resp = requests.post('http://localhost:8000/api/auth/login', json={
            'email': email,
            'password': '123456789'
        })
        if resp.status_code == 200:
            data = resp.json()
            user_data = data.get('user', {})
            has_access = bool(data.get('access_token'))
            has_refresh = bool(data.get('refresh_token'))
            print(f"[OK 200] {email:<25} | User ID: {user_data.get('id')} | Token: {data.get('token_type')} (access={has_access}, refresh={has_refresh})")
        else:
            all_success = False
            print(f"[FAIL {resp.status_code}] {email:<25} | Body: {resp.text}")

    # Test invalid password failure
    resp_bad = requests.post('http://localhost:8000/api/auth/login', json={
        'email': 'aryan@gmail.com',
        'password': 'wrong_password_999'
    })
    print(f"\n[Security Check] Invalid Password HTTP status: {resp_bad.status_code} (Expected 401)")
    assert resp_bad.status_code == 401, f"Expected 401, got {resp_bad.status_code}"

    # Test nonexistent email failure
    resp_none = requests.post('http://localhost:8000/api/auth/login', json={
        'email': 'nonexistent_user_999@gmail.com',
        'password': '123456789'
    })
    print(f"[Security Check] Nonexistent Email HTTP status: {resp_none.status_code} (Expected 401)")
    assert resp_none.status_code == 401, f"Expected 401, got {resp_none.status_code}"

    # Test email normalization (uppercase/mixed-case)
    resp_upper = requests.post('http://localhost:8000/api/auth/login', json={
        'email': '  ARYAN@GMAIL.COM  ',
        'password': '123456789'
    })
    print(f"[Normalization Check] Uppercase '  ARYAN@GMAIL.COM  ' HTTP status: {resp_upper.status_code} (Expected 200)")
    assert resp_upper.status_code == 200, f"Expected 200, got {resp_upper.status_code}"

    # Test authenticated GET /api/auth/me using issued access token
    access_token = resp_upper.json().get('access_token')
    resp_me = requests.get('http://localhost:8000/api/auth/me', headers={
        'Authorization': f'Bearer {access_token}'
    })
    print(f"[Protected Route Check] GET /api/auth/me HTTP status: {resp_me.status_code} (Expected 200)")
    assert resp_me.status_code == 200, f"Expected 200, got {resp_me.status_code}"
    print(f"Authenticated user: {resp_me.json().get('email')}")

    print(f"\n=== OVERALL API AUTH STATUS: {'ALL CHECKS PASSED' if all_success else 'FAILED'} ===")
    return all_success

if __name__ == '__main__':
    verify_logins()
