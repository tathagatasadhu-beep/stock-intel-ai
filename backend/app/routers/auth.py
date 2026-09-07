"""Investor accounts via Supabase Auth (email/password). /signup and /login proxy
Supabase's own auth API so the frontend never needs a Supabase key of its own (see
CLAUDE.md -> Conventions: Vercel only needs BACKEND_URL) — same pattern as EduQuestAI's
parent auth. The resulting access token is what get_current_user_claims verifies on every
other protected route (currently just Alerts)."""
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import get_current_user_claims
from app.core.supabase_client import get_supabase
from app.db.orm import AppUser
from app.db.session import get_db
from app.models.schemas import AuthToken, ForgotPasswordRequest, LoginRequest, SignupRequest, UserOut

router = APIRouter()


async def get_or_create_app_user(claims: dict = Depends(get_current_user_claims), db: AsyncSession = Depends(get_db)) -> AppUser:
    user_id = uuid.UUID(claims["sub"])
    result = await db.execute(select(AppUser).where(AppUser.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        user = AppUser(id=user_id, email=claims.get("email", ""))
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return user


@router.post("/signup", response_model=AuthToken)
async def signup(payload: SignupRequest, db: AsyncSession = Depends(get_db)):
    supabase = get_supabase()
    try:
        result = supabase.auth.sign_up({"email": payload.email, "password": payload.password})
    except Exception as exc:  # noqa: BLE001 - supabase-py raises its own AuthApiError subclass
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result.user is None:
        raise HTTPException(status_code=400, detail="Signup failed.")

    user_id = uuid.UUID(result.user.id)
    existing = await db.execute(select(AppUser).where(AppUser.id == user_id))
    if existing.scalar_one_or_none() is None:
        db.add(AppUser(id=user_id, email=payload.email))
        await db.commit()

    if result.session is None:
        raise HTTPException(status_code=202, detail="Signup succeeded — check your email to confirm your account, then log in.")

    return AuthToken(access_token=result.session.access_token, user=UserOut(id=str(user_id), email=payload.email))


@router.post("/login", response_model=AuthToken)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    supabase = get_supabase()
    try:
        result = supabase.auth.sign_in_with_password({"email": payload.email, "password": payload.password})
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail="Invalid email or password.") from exc

    user_id = uuid.UUID(result.user.id)
    existing = await db.execute(select(AppUser).where(AppUser.id == user_id))
    if existing.scalar_one_or_none() is None:
        db.add(AppUser(id=user_id, email=result.user.email))
        await db.commit()

    return AuthToken(access_token=result.session.access_token, user=UserOut(id=str(user_id), email=result.user.email))


@router.post("/forgot-password", status_code=202)
async def forgot_password(payload: ForgotPasswordRequest):
    """Always responds 202 regardless of whether the email is registered, so this
    endpoint can't be used to enumerate accounts. Supabase emails a recovery link to
    `{FRONTEND_URL}/reset-password`, which the frontend handles client-side — see that
    page for why (same exception to the BFF pattern as EduQuestAI's parent reset flow)."""
    supabase = get_supabase()
    try:
        supabase.auth.reset_password_for_email(
            payload.email, {"redirect_to": f"{settings.frontend_url}/reset-password"}
        )
    except Exception:  # noqa: BLE001 - never leak whether the email exists
        pass
    return {"detail": "If that email is registered, a reset link has been sent."}


@router.get("/me")
async def get_me(user: AppUser = Depends(get_or_create_app_user)):
    return {"id": str(user.id), "email": user.email}
