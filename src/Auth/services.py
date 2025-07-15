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
from .email import EmailSender



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
        
        # Convert provider_id to string if present
        if 'provider_id' in user_data_dict and user_data_dict['provider_id'] is not None:
            user_data_dict['provider_id'] = str(user_data_dict['provider_id'])
        
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
            # Get the existing user
            existing_user = await self.get_user_by_email(user_data.email, session)
            
            # If the user already authenticated with this provider, just return the user
            if existing_user.auth_provider == user_data.auth_provider:
                return existing_user
                
            # User exists but with different auth provider (likely email+password)
            # Link the accounts instead of rejecting
            if existing_user.auth_provider == "password" and user_data.auth_provider == "google":
                # Store the Google provider ID while keeping password auth
                existing_user.provider_id = user_data.provider_id
                
                # We'll keep auth_provider as "password" but add a field to track linked accounts
                # If you don't have this field, you can add it or use a separate table
                # For now, we'll just store the provider ID
                
                # Make sure the user is verified (since OAuth providers verify emails)
                existing_user.is_verified = True
                existing_user.updated_at = datetime.now()
                
                session.add(existing_user)
                await session.commit()
                await session.refresh(existing_user)
                
                return existing_user
                
            # If another OAuth provider, you could handle that case too
            # or keep the current behavior
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Email already in use with {existing_user.auth_provider} authentication"
            )
        
        # Create new user with OAuth as before
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
        
        # Check token expiration
        if "exp" in payload and datetime.fromtimestamp(payload["exp"]) < datetime.now():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Verification token has expired")
        
        # Find the user
        statement = select(User).where(User.uid == user_id)
        result = await session.execute(statement)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        # Mark as verified
        user.is_verified = True
        user.updated_at = datetime.now()
        
        # Find and delete all verification tokens for this user
        delete_statement = select(VerificationToken).where(VerificationToken.user_id == user_id)
        result = await session.execute(delete_statement)
        tokens = result.scalars().all()
        for token_obj in tokens:
            await session.delete(token_obj)
    
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
        access_token = create_access_token({
            "sub": str(user.uid),
            "email": user.email
        })
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
    
    async def create_refresh_token(self, user_id: uuid.UUID, session: AsyncSession, 
                                   previous_token_id: Optional[uuid.UUID] = None,
                                   family_id: Optional[uuid.UUID] = None) -> RefreshToken:
        """Create a refresh token for a user"""
        token_str = str(uuid.uuid4())
        expires_at = datetime.now() + timedelta(days=30)
        
        # If no family ID provided, create a new one
        if not family_id:
            family_id = uuid.uuid4()
        
        refresh_token = RefreshToken(
            user_id=user_id,
            token=token_str,
            family_id=family_id,
            previous_token_id=previous_token_id,
            expires_at=expires_at
        )
        
        session.add(refresh_token)
        await session.commit()
        await session.refresh(refresh_token)
        
        return refresh_token
    
    async def refresh_token(self, refresh_token: str, session: AsyncSession):
        """Generate a new access token using a refresh token and rotate the refresh token"""
        # First, find the token by its value only
        statement = select(RefreshToken).where(
            RefreshToken.token == refresh_token
        )
        result = await session.execute(statement)
        token = result.scalar_one_or_none()
        
        if not token:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, 
                detail="Invalid refresh token"
            )
        
        # Now check if it's revoked or expired - THIS IS THE TOKEN REUSE DETECTION
        if token.is_revoked or token.expires_at <= datetime.now():
            # TOKEN REUSE DETECTED! Take aggressive security measures
            
            # 1. Revoke all tokens in the same family (nuclear option)
            await self.revoke_token_family(token.family_id, session)
            
            # 2. Log the security event
            logging.warning(f"Refresh token reuse detected! User ID: {token.user_id}, Token ID: {token.id}")
            
            # 3. Alert the user
            statement = select(User).where(User.uid == token.user_id)
            result = await session.execute(statement)
            user = result.scalar_one_or_none()
            if user:
                await EmailSender.alert_user_about_token_reuse(user, token.user_id, session)
            
            # 4. Return a clear security message
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Security alert: Your session has been terminated due to suspicious activity. Please log in again."
            )
        
        # If we get here, the token is valid and not revoked - continue with normal flow
        # Get the user
        statement = select(User).where(User.uid == token.user_id)
        result = await session.execute(statement)
        user = result.scalar_one_or_none()
        
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        
        # Get the family ID from the current token
        family_id = token.family_id

        # Invalidate the current refresh token (rotation)
        token.is_revoked = True
        session.add(token)
        
        # Generate new refresh token in the same family
        new_refresh_token = await self.create_refresh_token(
            user_id=user.uid, 
            session=session,
            previous_token_id=token.id,
            family_id=family_id
        )
        
        # Generate new access token
        access_token = create_access_token({"sub": str(user.uid), "email": user.email})
        
        # Commit changes
        await session.commit()
        
        return {
            "access_token": access_token,
            "refresh_token": new_refresh_token.token,
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
    
    async def revoke_token_family(self, family_id: uuid.UUID, session: AsyncSession):
        """Revoke all tokens in a family (nuclear option)"""
        statement = select(RefreshToken).where(
            RefreshToken.family_id == family_id,
            RefreshToken.is_revoked == False
        )
        result = await session.execute(statement)
        tokens = result.scalars().all()
        
        for token in tokens:
            token.is_revoked = True
            session.add(token)
        
        await session.commit()
        return len(tokens)




