from sqlmodel.ext.asyncio.session import AsyncSession

from .schemas import *
from sqlmodel import select,desc
from src.StorageApp.models import FileModel
from datetime import datetime
from uuid import UUID
from typing import List, Optional

class StorageService:
    async def list_files(self,session:AsyncSession):
        """
        List all files in the storage.
        """
        statement = select(FileModel).order_by(desc(FileModel.created_at))
        result = await session.execute(statement)  # Changed from exec to execute
        files = result.scalars().all()  # Added scalars() method
        return files


    async def get_file(self, file_uuid: UUID, session: AsyncSession):
        """
        Retrieve a specific file by its UUID.
        """
        statement = select(FileModel).where(FileModel.uuid == file_uuid)
        result = await session.execute(statement)  # Changed from exec to execute
        file = result.scalar_one_or_none()  # Changed from one_or_none to scalar_one_or_none
        if not file:
            return None
        return file
    
    async def upload_file(self, file_upload: FileUploadSchema, session: AsyncSession):
        """
        Upload a file to the storage.
        """
        new_file = FileModel(
            name=file_upload.name,
            folder_path="store", # temporarily set to empty string, should be updated with actual path logic
            size=len(file_upload.file),
            created_at=datetime.now()
        )
        
        session.add(new_file)
        await session.commit()
        await session.refresh(new_file)
        
        return new_file