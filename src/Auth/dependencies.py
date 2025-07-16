from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel.ext.asyncio.session import AsyncSession
from .utils import decode_access_token
from .models import User
from sqlmodel import select
from DB.main import get_session
import uuid

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login")

async def get_current_user(
    token: str = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session)
) -> User:
    """Get the current authenticated user"""
    result = decode_access_token(token)
    
    # Check token status
    if result["status"] == "expired":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
            "code": "token_expired",
            "message": "Access token has expired"
        },
            headers={"WWW-Authenticate": "Bearer"},
        )
    elif result["status"] != "valid":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
            "code": "token_invalid",
            "message": "Invalid authentication credentials"
        },
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # If valid, get the payload
    payload = result["payload"]
    
    # Extract user ID directly from standardized payload
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Get the user
    statement = select(User).where(User.uid == user_id)
    result = await session.execute(statement)
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Inactive user",
        )
    
    return user