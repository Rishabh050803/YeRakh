from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlmodel import SQLModel,create_engine,text
from src.config import Config
from src.StorageApp.models import FileModel
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import AsyncEngine

engine = AsyncEngine(
    create_engine(
    url = Config.DATABASE_URL,
    echo = True,
))




async def init__db():
    async with engine.begin() as conn:
        
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session()->AsyncSession:
    Session = sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit = False
    )

    async with Session() as session:
        yield session