from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """
    Applies standard HTTP security headers to all responses.
    Configured to support embedded media (e.g. YouTube trailer modals).
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response: Response = await call_next(request)
        
        # Enforce MIME-type sniffing protection
        response.headers["X-Content-Type-Options"] = "nosniff"
        
        # Allow same-origin frame rendering (and child embeds like YouTube)
        response.headers["X-Frame-Options"] = "SAMEORIGIN"
        
        # Referrer Policy
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        
        # Legacy browser XSS protection
        response.headers["X-XSS-Protection"] = "1; mode=block"
        
        # Cross-Origin Opener Policy allowing popup dialogs for trailers
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin-allow-popups"
        
        return response
