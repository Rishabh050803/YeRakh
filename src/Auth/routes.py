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

class TokenRefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str

@auth_router.post("/register", status_code=status.HTTP_201_CREATED)
async def register(
    user_data: UserCreateModel_By_Password,
    session: AsyncSession = Depends(get_session)
):
    """
    Register a new user with email and password.
    
    This endpoint creates a new user account in the system and sends a verification email.
    The user must verify their email before they can fully use the system.
    
    Request Body:
        user_data (UserCreateModel_By_Password):
            - email: User's email address
            - first_name: User's first name
            - last_name: User's last name
            - password: User's password (will be hashed)
    
    Returns:
        JSON: A 201 Created response with:
            - message: Success message instructing to check email
            - user_id: UUID of the newly created user
    
    Raises:
        HTTPException (400): If the email is already registered
        HTTPException (422): If the request data fails validation
    
    Example:
        POST /auth/register
        {
            "email": "user@example.com",
            "first_name": "John",
            "last_name": "Doe",
            "password": "securepassword"
        }
    """

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
    """
    Login with email and password.
    
    This endpoint authenticates a user with their email and password,
    and returns access and refresh tokens for subsequent authenticated requests.
    
    Form Data:
        username: User's email address (note the field is named 'username' due to OAuth2 form requirements)
        password: User's password
    
    Returns:
        TokenResponse: A response containing:
            - access_token: JWT token for API access (expires in 10 minutes)
            - refresh_token: Token for obtaining new access tokens
            - token_type: Always "bearer"
            - user: Object containing user profile information:
                - email: User's email address
                - first_name: User's first name
                - last_name: User's last name
                - uid: User's unique identifier
                - is_verified: Boolean indicating email verification status
    
    Raises:
        HTTPException (401): If credentials are invalid
        HTTPException (403): If user account is inactive
    
    Example:
        POST /auth/login
        Form data: username=user@example.com&password=securepassword
    """
    
    return await user_service.login_with_password(form_data.username, form_data.password, session)

@auth_router.post("/login/google", response_model=TokenResponse)
async def login_with_google(
    request: GoogleAuthRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Login or register with Google OAuth.
    
    This endpoint verifies a Google ID token and either:
    1. Logs in an existing user who previously authenticated with Google
    2. Creates a new user account if this is their first login with Google
    
    Request Body:
        request (GoogleAuthRequest):
            - id_token: Google authentication ID token from frontend OAuth flow
    
    Returns:
        TokenResponse: A response containing:
            - access_token: JWT token for API access
            - refresh_token: Token for obtaining new access tokens
            - token_type: Always "bearer"
            - user: Object containing user profile information:
                - email: User's email address
                - first_name: User's first name
                - last_name: User's last name
                - uid: User's unique identifier
                - is_verified: Always true for OAuth users
    
    Raises:
        HTTPException (401): If the Google token is invalid
    
    Example:
        POST /auth/login/google
        {
            "id_token": "eyJhbGciOiJSUzI1..."
        }
    """
    # Verify the Google ID token
    user_info = await verify_google_token(request.id_token)
    
    if not user_info:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid Google authentication token"
        )
    
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
    
    # Update last login time
    user.last_login = datetime.now()
    session.add(user)
    await session.commit()
    
    return {
        "access_token": access_token,
        "refresh_token": refresh_token.token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "uid": str(user.uid),
            "is_verified": user.is_verified
        }
    }

@auth_router.post("/refresh", response_model=TokenRefreshResponse)
async def refresh_token(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Refresh an access token using a refresh token.
    
    This endpoint implements token rotation security:
    1. The current refresh token is invalidated
    2. A new access token is issued
    3. A new refresh token is issued
    
    This approach enhances security by limiting the window of opportunity if a refresh token is compromised.
    
    Request Body:
        request (RefreshRequest):
            - refresh_token: A valid refresh token previously issued
    
    Returns:
        TokenRefreshResponse: A response containing:
            - access_token: New JWT token for API access
            - refresh_token: New refresh token (the old one is invalidated)
            - token_type: Always "bearer"
    
    Raises:
        HTTPException (401): If the refresh token is invalid, expired, or already used
    
    Example:
        POST /auth/refresh
        {
            "refresh_token": "6afa95c4-c86e-4b1f-ac7f-fa55fb25e734"
        }
    """
    return await user_service.refresh_token(request.refresh_token, session)

@auth_router.post("/logout")
async def logout(
    request: RefreshRequest,
    session: AsyncSession = Depends(get_session)
):
    """
    Logout a user by revoking their refresh token.
    
    This endpoint invalidates the user's refresh token, effectively ending their session.
    Note that issued access tokens will still work until they expire (10 minutes by default).
    
    Request Body:
        request (RefreshRequest):
            - refresh_token: The refresh token to revoke
    
    Returns:
        JSON: A response with a logout confirmation message
    
    Raises:
        HTTPException (400): If the refresh token is invalid or already revoked
    
    Example:
        POST /auth/logout
        {
            "refresh_token": "6afa95c4-c86e-4b1f-ac7f-fa55fb25e734"
        }
    """
    return await user_service.logout(request.refresh_token, session)

@auth_router.get("/verify-email")
async def verify_email(
    token: str,
    session: AsyncSession = Depends(get_session)
):
    """
    Verify a user's email address using a verification token.
    
    This endpoint is typically accessed via a link sent to the user's email.
    It validates the token and marks the user's email as verified if valid.
    
    Query Parameters:
        token (str): The email verification token sent to the user's email
    
    Returns:
        JSON: A success message if verification was successful
    
    Raises:
        HTTPException (400): If the token is invalid or expired
        HTTPException (404): If the associated user doesn't exist
    
    Example:
        GET /auth/verify-email?token=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
    """
    user = await user_service.verify_email(token, session)
    return {"message": "Email verified successfully"}