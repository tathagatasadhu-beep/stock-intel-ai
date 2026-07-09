"""
JWT verification for signed-in investor accounts, authenticated through Supabase Auth
(email/password). Same pattern as EduQuestAI's app/core/security.py::decode_supabase_jwt —
Supabase signs access tokens with its own key (asymmetric ES256/RS256), published at
/auth/v1/.well-known/jwks.json, so we verify against that JWKS rather than holding a shared secret.
"""
from typing import Any

import jwt
from fastapi import Header, HTTPException

from app.core.config import settings

_jwks_client = jwt.PyJWKClient(f"{settings.supabase_url}/auth/v1/.well-known/jwks.json") if settings.supabase_url else None


def decode_supabase_jwt(token: str) -> dict[str, Any]:
    if _jwks_client is None:
        raise HTTPException(status_code=500, detail="SUPABASE_URL is not configured.")
    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        return jwt.decode(
            token,
            signing_key.key,
            algorithms=["ES256", "RS256"],
            audience="authenticated",
            leeway=30,
        )
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"Invalid or expired token: {exc}") from exc


async def get_current_user_claims(authorization: str = Header(default="")) -> dict[str, Any]:
    """FastAPI dependency: verifies the Authorization: Bearer <token> header, returns Supabase claims."""
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing bearer token.")
    token = authorization.removeprefix("Bearer ").strip()
    return decode_supabase_jwt(token)
