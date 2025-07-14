from .models import User, VerificationToken, RefreshToken
from .schemas import UserCreateModel_By_OAuth, UserCreateModel_By_Password, LoginResponse
from .utils import generate_password_hash, verify_password, create_access_token, create_verification_token, verify_token
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select
from fastapi.exceptions import HTTPException
from fastapi import status
from datetime import datetime, timedelta
import uuid
import logging
from typing import Optional

class UserService:
    async def get_user_by_email(self, email: str, session: AsyncSession):
        statement = select(User).where(User.email == email)
        result = await session.execute(statement)
        user = result.scalar_one_or_none()
        return user
    
    async def user_exists(self, email: str, session: AsyncSession) -> bool:
        """Check if a user exists by email."""
        user = await self.get_user_by_email(email, session)
        return True if user else False
    
    async def create_user_by_password(self, user_data: UserCreateModel_By_Password, session: AsyncSession):
        if await self.user_exists(user_data.email, session):
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="A user with same email exists")
        
        user_data_dict = user_data.model_dump()

        # Remove password from dict
        password = user_data_dict.pop('password')
        
        new_user = User(**user_data_dict)
        new_user.password_hash = generate_password_hash(password)
        
        session.add(new_user)
        await session.commit()
        await session.refresh(new_user)
        
        # Create verification token
        await self.create_verification_token(new_user.uid, session)
        
        return new_user
    
    async def create_user_by_Oauth(self, user_data: UserCreateModel_By_OAuth, session: AsyncSession):
        if await self.user_exists(user_data.email, session):
            # For OAuth, check if user exists but has a different auth provider
            existing_user = await self.get_user_by_email(user_data.email, session)
            if existing_user.auth_provider != user_data.auth_provider:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Email already in use with {existing_user.auth_provider} authentication"
                )
            return existing_user
        
        user = User(
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            auth_provider=user_data.auth_provider,
            provider_id=user_data.provider_id,
            is_verified=True,  # OAuth users are verified by default
            is_active=True,
            password_hash="",  # OAuth users don't have passwords
            created_at=datetime.now(),
            updated_at=datetime.now(),
            last_login=datetime.now()
        )

        session.add(user)
        await session.commit()
        await session.refresh(user)

        return user
    
    # Add verification token methods
    async def create_verification_token(self, user_id: uuid.UUID, session: AsyncSession) -> VerificationToken:
        """Create and store a verification token"""
        token_str = create_verification_token(user_id)
        expires_at = datetime.now() + timedelta(hours=24)
        
        verification = VerificationToken(
            user_id=user_id,
            token=token_str,
            expires_at=expires_at
        )
        
        session.add(verification)
        await session.commit()
        await session.refresh(verification)
        
        return verification
    
    async def verify_email(self, token: str, session: AsyncSession) -> Optional[User]:
        """Verify a user's email with the given token"""
        # Decode the token
        payload = verify_token(token)
        if not payload or payload.get("type") != "email_verification":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid verification token")
        
        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token payload")
        
        # Find the user
        statement = select(User).where(User.uid == user_id)
        result = await session.execute(statement)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        # Mark as verified
        user.is_verified = True
        user.updated_at = datetime.now()
        
        session.add(user)
        await session.commit()
        await session.refresh(user)
        
        return user
    
    # Login methods
    async def login_with_password(self, email: str, password: str, session: AsyncSession):
        """Login with email and password"""
        user = await self.get_user_by_email(email, session)
        
        if not user:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        if user.auth_provider != "password":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"This account uses {user.auth_provider} authentication"
            )
        
        if not verify_password(password, user.password_hash):
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
        
        if not user.is_verified:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Email not verified")
        
        # Update last login
        user.last_login = datetime.now()
        session.add(user)
        await session.commit()
        
        # Generate tokens
        access_token = create_access_token({"sub": str(user.uid), "email": user.email})
        refresh_token = await self.create_refresh_token(user.uid, session)
        
        return {
            "access_token": access_token,
            "refresh_token": refresh_token.token,
            "token_type": "bearer",
            "user": {
                "email": user.email,
                "first_name": user.first_name,
                "last_name": user.last_name,
            }
        }
    
    async def create_refresh_token(self, user_id: uuid.UUID, session: AsyncSession) -> RefreshToken:
        """Create a refresh token for a user"""
        token_str = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(days=30)
        
        refresh_token = RefreshToken(
            user_id=user_id,
            token=token_str,
            expires_at=expires_at
        )
        
        session.add(refresh_token)
        await session.commit()
        await session.refresh(refresh_token)
        
        return refresh_token
    
    async def refresh_token(self, refresh_token: str, session: AsyncSession):
        """Generate a new access token using a refresh token"""
        # Find the token
        statement = select(RefreshToken).where(
            RefreshToken.token == refresh_token,
            RefreshToken.is_revoked == False,
            RefreshToken.expires_at > datetime.now()
        )
        result = await session.execute(statement)
        token = result.scalar_one_or_none()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid or expired refresh token"
            )
        
        # Get the user
        statement = select(User).where(User.uid == token.user_id)
        result = await session.execute(statement)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        # Generate new access token
        access_token = create_access_token({"sub": str(user.uid), "email": user.email})
        
        return {
            "access_token": access_token,
            "token_type": "bearer"
        }
    
    async def logout(self, refresh_token: str, session: AsyncSession):
        """Revoke a refresh token to log the user out"""
        statement = select(RefreshToken).where(RefreshToken.token == refresh_token)
        result = await session.execute(statement)
        token = result.scalar_one_or_none()
        
        if token:
            token.is_revoked = True
            session.add(token)
            await session.commit()
        
        return {"message": "Successfully logged out"}


