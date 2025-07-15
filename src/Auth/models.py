from sqlmodel import SQLModel, Field, Column, Relationship
import uuid
from datetime import datetime
import sqlalchemy.dialects.postgresql as pg
from typing import Optional

class User(SQLModel,table=True):
    __tablename__ ="users"
    uid:uuid.UUID = Field(
        sa_column = Column(
            pg.UUID,
            nullable = False,
            primary_key = True,
            default = uuid.uuid4,
        ))
    email : str
    first_name : str
    last_name : str
    is_verified : bool = Field(default=False)
    is_active : bool = Field(default=True)
    password_hash : str 
    auth_provider: str = Field(default="password")  # e.g., "password", "google", "github"
    provider_id: Optional[str] = Field(default=None)  # ID from the provider
    created_at : datetime = Field(sa_column=  Column(pg.TIMESTAMP,default = datetime.now))
    updated_at : datetime= Field( sa_column= Column(pg.TIMESTAMP,default = datetime.now))
    last_login : datetime = Field(sa_column= Column(pg.TIMESTAMP,default = datetime.now))

    def __repr__(self):
        return f"<User {self.email}> , first name - {self.first_name}, last name - {self.last_name}"

class VerificationToken(SQLModel, table=True):
    __tablename__ = "verification_tokens"
    id: uuid.UUID = Field(
        sa_column=Column(
            pg.UUID, 
            nullable=False,
            primary_key=True,
            default=uuid.uuid4,
        ))
    user_id: uuid.UUID = Field(foreign_key="users.uid")
    token: str = Field(index=True)
    expires_at: datetime
    created_at: datetime = Field(sa_column=Column(pg.TIMESTAMP, default=datetime.now))

class RefreshToken(SQLModel, table=True):
    __tablename__ = "refresh_tokens"
    id: uuid.UUID = Field(
        sa_column=Column(
            pg.UUID,
            nullable=False,
            primary_key=True, 
            default=uuid.uuid4,
        ))
    user_id: uuid.UUID = Field(foreign_key="users.uid")
    token: str = Field(index=True)
    family_id: uuid.UUID = Field(default_factory=uuid.uuid4)  # Add this field
    previous_token_id: Optional[uuid.UUID] = Field(default=None)  # Add this field
    expires_at: datetime
    is_revoked: bool = Field(default=False)
    created_at: datetime = Field(sa_column=Column(pg.TIMESTAMP, default=datetime.now))