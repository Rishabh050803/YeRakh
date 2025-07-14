from fastapi import APIRouter, Depends, HTTPException, status, Body, Request
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel.ext.asyncio.session import AsyncSession
from typing import Optional
from .services import UserService
from .schemas import UserCreateModel_By_Password, UserCreateModel_By_OAuth
from DB.main import get_session
from pydantic import BaseModel, EmailStr
from .utils import *
import json
from datetime import datetime
from .models import VerificationToken, RefreshToken
from sqlmodel import select

auth_router = APIRouter()
user_service = UserService()

class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: dict

class RefreshRequest(BaseModel):
    refresh_token: str

class GoogleAuthRequest(BaseModel):
    id_token: str

@auth_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreateModel_By_Password,
    session: AsyncSession = Depends(get_session)
):
    """Register a new user with email and password"""
    user = await user_service.create_user_by_password(user_data, session)
    
    # In a real app, you would send an email with the verification link here
    statement = select(VerificationToken).where(VerificationToken.user_id == user.uid)
    result = await session.execute(statement)
    verification = result.scalar_one_or_none()
    if verification:
        from .email import EmailSender
        await EmailSender.send_verification_email(
            email=user.email,
            token=verification.token,
        )
    return {
        "message": "User registered successfully. Please check your email to verify your account.",
        "user_id": str(user.uid)
    }

@auth_router.post("/login", response_model=TokenResponse)
async def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    session: AsyncSession = Depends(get_session)
):
    """Login with email and password"""
    return await user_service.login_with_password(form_data.username, form_data.password, session)

@auth_router.post("/login/google", response_model=TokenResponse)
async def login_with_google(
    request: GoogleAuthRequest,
    session: AsyncSession = Depends(get_session)
):
    """Login with Google OAuth"""
    # In a real implementation, you would verify the Google ID token
    # and extract user information
    
    # Mock implementation for example
    user_info = {
        "email": "user@example.com",
        "first_name": "John",
        "last_name": "Doe",
        "provider_id": "123456789"
    }
    
    # Create or get user
    oauth_user = UserCreateModel_By_OAuth(
        email=user_info["email"],
        first_name=user_info["first_name"],
        last_name=user_info["last_name"],
        auth_provider="google",
        provider_id=user_info["provider_id"]
    )
    
    user = await user_service.create_user_by_Oauth(oauth_user, session)
    
    # Generate tokens
    access_token = create_access_token({"sub": str(user.uid), "email": user.email})
    refresh_token = await user_service.create_refresh_token(user.uid, session)
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token.token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name
        }
    }

@auth_router.post("/refresh")
async def refresh_token(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session)
):
    """Refresh an access token"""
    return await user_service.refresh_token(request.refresh_token, session)

@auth_router.post("/logout")
async def logout(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session)
):
    """Logout by revoking the refresh token"""
    return await user_service.logout(request.refresh_token, session)

@auth_router.get("/verify-email")
async def verify_email(
    token: str,
    session: AsyncSession = Depends(get_session)
):
    """Verify a user's email address"""
    user = await user_service.verify_email(token, session)
    return {"message": "Email verified successfully"}