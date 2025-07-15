from pydantic import BaseModel, Field, EmailStr
import uuid
from datetime import datetime
from typing import Optional

# Add response models
class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: dict

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str
    user: dict

class UserResponse(BaseModel):
    uid: uuid.UUID
    email: str
    first_name: str
    last_name: str
    is_verified: bool
    created_at: datetime


class UserCreateModel_By_Password(BaseModel):
    email: str = Field(max_length=100)
    first_name: str = Field(max_length=50)
    last_name: str = Field(max_length=50)
    password: str = Field(min_length=8, max_length=128)
    auth_provider: str = Field(default="password")
    provider_id: Optional[str] = Field(default=None)  # Changed from int to Optional[str]
    is_verified: bool = Field(default=False)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_login: datetime = Field(default_factory=datetime.now)


class UserCreateModel_By_OAuth(BaseModel):
    email: str = Field(max_length=100)
    first_name: str = Field(max_length=50)
    last_name: str = Field( max_length=50)
    auth_provider: str   # e.g., "google", "github"
    provider_id: str  # Unique identifier from the OAuth provider
    is_verified: bool = Field(default=True)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    last_login: datetime = Field(default_factory=datetime.now)



