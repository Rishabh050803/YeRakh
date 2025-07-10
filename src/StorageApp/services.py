from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc
from src.StorageApp.models import FileModel
from storage.disk_services import DiskManager  
from datetime import datetime
from uuid import UUID, uuid4
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse
import os

class StorageService:
    async def list_files(self, session: AsyncSession):
        """
        List all files in the storage.
        """
        statement = select(FileModel).order_by(desc(FileModel.created_at))
        result = await session.execute(statement)
        return result.scalars().all()

    async def get_file(self, file_uuid: UUID, session: AsyncSession):
        """
        Get file model by UUID.
        """
        statement = select(FileModel).where(FileModel.uuid == file_uuid)
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_file_response(self, file_uuid: UUID, session: AsyncSession):
        """
        Return a FileResponse from disk for a given file UUID.
        """
        file = await self.get_file(file_uuid, session)
        if not file or not DiskManager.file_exists(file.name):
            return None

        return DiskManager.get_file_response(file.name)

    async def upload_file(self, file: UploadFile, folder_path: str, session: AsyncSession):
        """
        Upload file to disk and store metadata in DB with folder path.
        """
        # Check if file with same name exists in the same folder
        # First check if a file with the same name exists in the database
        print("folder_path for file upload ", folder_path)
        statement = select(FileModel).where(
            (FileModel.name == file.filename) & 
            (FileModel.folder_path == folder_path)
        )
        result = await session.execute(statement)
        existing_file = result.scalar_one_or_none()
        
        if existing_file:
            # File already exists - return error
            raise HTTPException(
                status_code=409,
                detail=f"File '{file.filename}' already exists in folder '{folder_path}'"
            )
        
        # Read file content
        content = await file.read()
        
        # Store metadata in DB
        new_file = FileModel(
            name=file.filename,
            folder_path=folder_path,  # Use the provided folder path
            size=len(content),
            created_at=datetime.now()
        )
        
        session.add(new_file)
        await session.commit()
        await session.refresh(new_file)
        
        # Save file to disk - all files stored in the same physical directory
        DiskManager.save_file(file.filename, content)
        
        return new_file

    async def delete_file(self, file_uuid: UUID, session: AsyncSession):
        """
        Delete the file from disk and DB.
        """
        file = await self.get_file(file_uuid, session)
        if not file:
            return None

        # Delete from disk
        DiskManager.delete_file(file.name)

        # Delete from DB
        await session.delete(file)
        await session.commit()

        return file


    async def explore_folder(self, folder_path: str, session: AsyncSession):
        # print("folder_path", folder_path)
        folder_path = folder_path.rstrip("/")
        stmt = select(FileModel).where(FileModel.folder_path.startswith(folder_path))

        result = await session.execute(stmt)
        all_items = result.scalars().all()
        # print("result of the query",all_items)

        files = []
        folders = set()

        for item in all_items:
            item_folder = item.folder_path.rstrip("/")

            if item_folder == folder_path:
                # This file is in the current folder
                files.append({
                    "type": "file",
                    "name": item.name,
                    "path": os.path.join(item.folder_path, item.name)
                })
            else:
                # This file is deeper, identify its immediate subfolder
                rel_path = item_folder[len(folder_path):].lstrip("/")  # Remove current path
                parts = rel_path.split("/")
                if parts and parts[0]:
                    folders.add(parts[0])

        folder_list = [{
            "type": "folder",
            "name": folder,
            "path": os.path.join(folder_path, folder)
        } for folder in sorted(folders)]

        files = sorted(files, key=lambda x: x['name'].lower())
        return folder_list + files


    async def delete_folder(self, folder_path: str, session: AsyncSession):
        """
        Delete all files in a folder and the folder itself.
        """
        # Get all files in the folder
        stmt = select(FileModel).where(FileModel.folder_path == folder_path)
        result = await session.execute(stmt)
        files = result.scalars().all()

        if not files:
            raise HTTPException(status_code=404, detail="Folder not found or empty")

        # Delete each file
        for file in files:
            DiskManager.delete_file(file.name)
            await session.delete(file)

        await session.commit()
        return {"message": "Folder and its contents deleted successfully"}