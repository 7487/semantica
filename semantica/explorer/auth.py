"""
Semantica Explorer : Authentication Middleware

Provides opt-in API key authentication for all Explorer API routes.

Enable by setting the ``EXPLORER_API_KEY`` environment variable. When set,
every request to ``/api/*`` must include either:

- An ``Authorization: Bearer <key>`` header, or
- An ``X-API-Key: <key>`` header.

When ``EXPLORER_API_KEY`` is not set, authentication is disabled and the
Explorer operates in open/development mode (with a startup warning).
"""

import hmac
import logging
import os
from typing import Optional

from fastapi import HTTPException, Request, status
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

_logger = logging.getLogger(__name__)


def _get_api_key() -> Optional[str]:
    """Read the configured API key from the environment."""
    return os.environ.get("EXPLORER_API_KEY")


def _extract_token(request: Request) -> Optional[str]:
    """Extract the API key from the request headers."""
    # Check Authorization: Bearer <key>
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # Check X-API-Key: <key>
    api_key_header = request.headers.get("X-API-Key", "")
    if api_key_header:
        return api_key_header.strip()

    return None


class APIKeyAuthMiddleware(BaseHTTPMiddleware):
    """
    Middleware that enforces API key authentication on ``/api/*`` routes.

    Skips authentication for:
    - Non-API routes (static files, health checks, WebSocket, docs)
    - OPTIONS requests (CORS preflight)
    - When ``EXPLORER_API_KEY`` is not configured (open mode)
    """

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        api_key = _get_api_key()

        # If no API key is configured, allow all requests (open mode)
        if not api_key:
            return await call_next(request)

        # Skip authentication for non-API paths
        path = request.url.path
        if not path.startswith("/api/"):
            return await call_next(request)

        # Skip CORS preflight
        if request.method == "OPTIONS":
            return await call_next(request)

        # Validate the token
        token = _extract_token(request)
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing API key. Provide via 'Authorization: Bearer <key>' or 'X-API-Key: <key>' header.",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # Constant-time comparison to prevent timing attacks
        if not hmac.compare_digest(token, api_key):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Invalid API key.",
            )

        return await call_next(request)


def warn_if_unauthenticated() -> None:
    """Log a warning at startup if no API key is configured."""
    if not _get_api_key():
        _logger.warning(
            "EXPLORER_API_KEY is not set. The Explorer API is running WITHOUT "
            "authentication. Set EXPLORER_API_KEY to enable API key protection "
            "for all /api/* endpoints."
        )
