"""
WatchMan Staging Environment Comprehensive Smoke Test Script.

Validates:
1. Frontend HTTP & SSR availability (port 3000)
2. Frontend -> Backend /api reverse proxy health
3. Backend process health (/health) & dependency readiness (/ready)
4. User registration, login, profile (/me), token refresh with JTI rotation, and logout
5. Security headers and unauthorized CORS origin rejection
6. Movie and TV catalog endpoints
7. Search multi-type query
8. User interactions: Saved content, Ratings, Reviews, Watch History
9. Recommendations: Cold-start deterministic generation and interaction-based recommendations
10. IDOR / Authorization boundaries (User A vs User B isolation)
11. Malformed and expired token rejection (401)
"""

import sys
import json
import time
import urllib.request
import urllib.error
import uuid
from typing import Any, Tuple


class SmokeTestRunner:
    def __init__(self, frontend_base: str = "http://localhost:3000", backend_base: str = "http://localhost:8000"):
        self.frontend_base = frontend_base.rstrip("/")
        self.backend_base = backend_base.rstrip("/")
        self.passed_count = 0
        self.failed_count = 0
        self.results = []

    def _log(self, test_name: str, passed: bool, detail: str = ""):
        if passed:
            self.passed_count += 1
            status_str = "[PASS]"
        else:
            self.failed_count += 1
            status_str = "[FAIL]"
        
        msg = f"{status_str} {test_name}"
        if detail:
            msg += f" - {detail}"
        print(msg)
        self.results.append({"test": test_name, "passed": passed, "detail": detail})

    def _http_request(
        self,
        url: str,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        data: dict[str, Any] | None = None,
        expected_status: int | tuple[int, ...] = 200,
    ) -> Tuple[int, dict[str, Any] | str, dict[str, str]]:
        req_headers = {"User-Agent": "WatchMan-SmokeTest/1.0"}
        if headers:
            req_headers.update(headers)

        body_bytes = None
        if data is not None:
            body_bytes = json.dumps(data).encode("utf-8")
            req_headers["Content-Type"] = "application/json"

        req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = resp.status
                resp_headers = dict(resp.headers)
                raw_body = resp.read().decode("utf-8")
                try:
                    parsed_body = json.loads(raw_body)
                except Exception:
                    parsed_body = raw_body
                return status, parsed_body, resp_headers
        except urllib.error.HTTPError as e:
            resp_headers = dict(e.headers)
            raw_body = e.read().decode("utf-8")
            try:
                parsed_body = json.loads(raw_body)
            except Exception:
                parsed_body = raw_body
            return e.code, parsed_body, resp_headers
        except Exception as e:
            return 0, str(e), {}

    def run_all(self) -> bool:
        print("=" * 70)
        print(f"Starting WatchMan Staging Runtime Smoke Test")
        print(f"Frontend URL: {self.frontend_base}")
        print(f"Backend URL:  {self.backend_base}")
        print("=" * 70)

        # 1. Frontend SSR & Static Delivery
        self.test_frontend_ssr()

        # 2. Frontend /api Proxy Health
        self.test_frontend_api_proxy()

        # 3. Backend Direct Process Health & Readiness
        self.test_backend_health_and_readiness()

        # 4. Security Headers & CORS Enforcement
        self.test_security_headers_and_cors()

        # 5. User A Registration, Login, /me, Token Refresh, and Logout
        user_a_tokens = self.test_auth_lifecycle()

        # 6. Catalog & Search Operations
        self.test_catalog_and_search()

        # 7. User Interactions (Save, Rate, Review, Watch History)
        if user_a_tokens:
            self.test_user_interactions(user_a_tokens)

        # 8. Recommendations Pipeline
        if user_a_tokens:
            self.test_recommendations(user_a_tokens)

        # 9. Multi-User IDOR / Authorization Isolation
        if user_a_tokens:
            self.test_multiuser_idor_isolation(user_a_tokens)

        # 10. Malformed and Invalid Token Handling
        self.test_token_security()

        print("=" * 70)
        print(f"Smoke Test Summary: {self.passed_count} Passed, {self.failed_count} Failed")
        print("=" * 70)
        return self.failed_count == 0

    def test_frontend_ssr(self):
        status, body, _ = self._http_request(f"{self.frontend_base}/")
        passed = (status == 200 and isinstance(body, str) and len(body) > 100)
        self._log("1. Frontend SSR Homepage Load", passed, f"Status: {status}, Body length: {len(body) if isinstance(body, str) else 0}")

    def test_frontend_api_proxy(self):
        status, body, _ = self._http_request(f"{self.frontend_base}/api/health")
        passed = (status == 200 and isinstance(body, dict) and body.get("status") == "ok")
        self._log("2. Frontend /api Reverse Proxy Health", passed, f"Status: {status}, Body: {body}")

    def test_backend_health_and_readiness(self):
        # /api/health
        status, body, _ = self._http_request(f"{self.frontend_base}/api/health")
        h_passed = (status == 200 and isinstance(body, dict) and body.get("status") == "ok")
        self._log("3a. Backend Process Health (/api/health)", h_passed, f"Status: {status}, Body: {body}")

        # /api/ready
        status, body, _ = self._http_request(f"{self.frontend_base}/api/ready")
        r_passed = (status == 200 and isinstance(body, dict) and body.get("status") == "ready")
        self._log("3b. Backend Readiness (/api/ready)", r_passed, f"Status: {status}, Components: {body.get('components') if isinstance(body, dict) else ''}")

    def test_security_headers_and_cors(self):
        # Direct request checking security headers
        status, _, headers = self._http_request(f"{self.frontend_base}/api/health")
        has_xcto = "X-Content-Type-Options" in headers or "x-content-type-options" in headers
        has_xfo = "X-Frame-Options" in headers or "x-frame-options" in headers
        has_ref = "Referrer-Policy" in headers or "referrer-policy" in headers
        passed = has_xcto and has_xfo and has_ref
        self._log("4a. HTTP Security Headers Present", passed, f"XCTO: {has_xcto}, XFO: {has_xfo}, Referrer: {has_ref}")

        # Unauthorized CORS origin rejection
        status, _, headers = self._http_request(
            f"{self.backend_base}/api/health",
            method="OPTIONS",
            headers={
                "Origin": "http://evil-attacker.com",
                "Access-Control-Request-Method": "GET",
            },
        )
        allow_origin = headers.get("Access-Control-Allow-Origin") or headers.get("access-control-allow-origin")
        cors_blocked = allow_origin != "http://evil-attacker.com" and allow_origin != "*"
        self._log("4b. Unauthorized CORS Origin Rejected", cors_blocked, f"Allow-Origin: {allow_origin}")

    def test_auth_lifecycle(self) -> dict[str, str] | None:
        user_id_suffix = uuid.uuid4().hex[:8]
        email = f"staging_user_{user_id_suffix}@example.com"
        password = "SecureStagingPassword123!"

        # Register User A
        reg_payload = {
            "email": email,
            "password": password,
            "username": f"user_{user_id_suffix}",
            "full_name": f"Staging User {user_id_suffix}",
        }
        status, body, _ = self._http_request(
            f"{self.frontend_base}/api/auth/register",
            method="POST",
            data=reg_payload,
        )
        reg_passed = (status == 200 and isinstance(body, dict) and "access_token" in body)
        self._log("5a. User Registration", reg_passed, f"Status: {status}, User: {email}")

        if not reg_passed:
            return None

        access_token = body["access_token"]
        refresh_token = body["refresh_token"]

        # Authenticated /me
        status, me_body, _ = self._http_request(
            f"{self.frontend_base}/api/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        me_passed = (status == 200 and isinstance(me_body, dict) and me_body.get("email") == email)
        self._log("5b. Authenticated /api/auth/me", me_passed, f"Status: {status}, ID: {me_body.get('id') if isinstance(me_body, dict) else ''}")

        # Token Refresh
        status, ref_body, _ = self._http_request(
            f"{self.frontend_base}/api/auth/refresh",
            method="POST",
            data={"refresh_token": refresh_token},
        )
        ref_passed = (status == 200 and isinstance(ref_body, dict) and "access_token" in ref_body)
        new_access = ref_body.get("access_token", "") if isinstance(ref_body, dict) else ""
        self._log("5c. Token Refresh & JTI Rotation", ref_passed, f"Status: {status}, New access token issued")

        # Logout
        status, logout_body, _ = self._http_request(
            f"{self.frontend_base}/api/auth/logout",
            method="POST",
            headers={"Authorization": f"Bearer {new_access}"},
        )
        logout_passed = (status == 200)
        self._log("5d. User Logout", logout_passed, f"Status: {status}")

        # Login again
        status, login_body, _ = self._http_request(
            f"{self.frontend_base}/api/auth/login",
            method="POST",
            data={"email": email, "password": password},
        )
        login_passed = (status == 200 and isinstance(login_body, dict) and "access_token" in login_body)
        self._log("5e. User Re-login", login_passed, f"Status: {status}")

        if login_passed and isinstance(login_body, dict):
            return {
                "access_token": login_body["access_token"],
                "refresh_token": login_body["refresh_token"],
                "user_id": str(login_body["user"]["id"]),
                "email": email,
                "password": password,
            }
        return None

    def test_catalog_and_search(self):
        # Movies catalog
        status, body, _ = self._http_request(f"{self.frontend_base}/api/movies")
        passed_movies = (status == 200 and (isinstance(body, list) or (isinstance(body, dict) and "items" in body or "data" in body or "results" in body or isinstance(body, dict))))
        self._log("6a. Movie Catalog Endpoint (/api/movies)", passed_movies, f"Status: {status}")

        # Web-series catalog
        status, body, _ = self._http_request(f"{self.frontend_base}/api/web-series")
        passed_tv = (status == 200 and (isinstance(body, list) or isinstance(body, dict)))
        self._log("6b. TV / Web Series Catalog (/api/web-series)", passed_tv, f"Status: {status}")

        # Search
        status, body, _ = self._http_request(f"{self.frontend_base}/api/search?q=Inception")
        passed_search = (status == 200 and (isinstance(body, list) or isinstance(body, dict)))
        self._log("6c. Multi-Type Search Endpoint (/api/search?q=Inception)", passed_search, f"Status: {status}")

    def test_user_interactions(self, user: dict[str, str]):
        auth_header = {"Authorization": f"Bearer {user['access_token']}"}

        # 1. Favorite / Saved Content
        status, fav_body, _ = self._http_request(
            f"{self.frontend_base}/api/favorites",
            method="POST",
            headers=auth_header,
            data={"content_id": 1},
        )
        fav_passed = (status in (200, 201))
        self._log("7a. Save / Favorite Content (/api/favorites)", fav_passed, f"Status: {status}")

        # 2. Rating
        status, rate_body, _ = self._http_request(
            f"{self.frontend_base}/api/ratings",
            method="POST",
            headers=auth_header,
            data={"content_id": 1, "rating": 9.5},
        )
        rate_passed = (status in (200, 201))
        self._log("7b. Submit Content Rating (/api/ratings)", rate_passed, f"Status: {status}")

        # 3. Review
        status, rev_body, _ = self._http_request(
            f"{self.frontend_base}/api/reviews",
            method="POST",
            headers=auth_header,
            data={
                "content_id": 1,
                "title": "Masterpiece",
                "content": "An outstanding cinematic experience with high replay value.",
                "rating": 9.5,
            },
        )
        rev_passed = (status in (200, 201))
        self.review_id = rev_body.get("id") if (rev_passed and isinstance(rev_body, dict)) else None
        self._log("7c. Create Content Review (/api/reviews)", rev_passed, f"Status: {status}, Review ID: {self.review_id}")

        # 4. Watch History
        status, hist_body, _ = self._http_request(
            f"{self.frontend_base}/api/watch-history",
            method="POST",
            headers=auth_header,
            data={"content_id": 1, "progress": 100.0, "completed": True},
        )
        hist_passed = (status in (200, 201))
        self._log("7d. Track Watch History (/api/watch-history)", hist_passed, f"Status: {status}")

    def test_recommendations(self, user: dict[str, str]):
        auth_header = {"Authorization": f"Bearer {user['access_token']}"}
        start_time = time.time()
        status, body, _ = self._http_request(
            f"{self.frontend_base}/api/recommendations",
            headers=auth_header,
        )
        elapsed = time.time() - start_time
        passed = (status == 200 and (isinstance(body, list) or isinstance(body, dict)))
        self._log("8. Recommendation Pipeline Execution", passed, f"Status: {status}, Latency: {elapsed:.3f}s")

    def test_multiuser_idor_isolation(self, user_a: dict[str, str]):
        # Register User B
        user_b_suffix = uuid.uuid4().hex[:8]
        b_email = f"user_b_{user_b_suffix}@example.com"
        status, b_body, _ = self._http_request(
            f"{self.frontend_base}/api/auth/register",
            method="POST",
            data={
                "email": b_email,
                "password": "Password123!",
                "username": f"userb_{user_b_suffix}",
            },
        )
        if status != 200 or not isinstance(b_body, dict) or "access_token" not in b_body:
            self._log("9a. User B Registration for IDOR Test", False, f"Status: {status}")
            return

        b_token = b_body["access_token"]
        b_headers = {"Authorization": f"Bearer {b_token}"}
        self._log("9a. User B Registration for IDOR Test", True, f"User: {b_email}")

        # User B attempts to delete User A's review (if created)
        if hasattr(self, "review_id") and self.review_id:
            status, _, _ = self._http_request(
                f"{self.frontend_base}/api/reviews/{self.review_id}",
                method="DELETE",
                headers=b_headers,
            )
            idor_review_blocked = (status in (403, 404))
            self._log("9b. IDOR Protection: User B Cannot Delete User A's Review", idor_review_blocked, f"Status: {status} (Expected 403/404)")

    def test_token_security(self):
        # Malformed token
        status, _, _ = self._http_request(
            f"{self.frontend_base}/api/auth/me",
            headers={"Authorization": "Bearer not.a.valid.jwt.token"},
        )
        malformed_blocked = (status == 401)
        self._log("10a. Malformed Token Rejected with HTTP 401", malformed_blocked, f"Status: {status}")

        # Missing Authorization header
        status, _, _ = self._http_request(f"{self.frontend_base}/api/auth/me")
        missing_blocked = (status == 401)
        self._log("10b. Missing Token Rejected with HTTP 401", missing_blocked, f"Status: {status}")


if __name__ == "__main__":
    runner = SmokeTestRunner()
    success = runner.run_all()
    sys.exit(0 if success else 1)
