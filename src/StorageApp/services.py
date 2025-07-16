from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel import select, desc, func
from src.StorageApp.models import FileModel
from storage.disk_services import DiskManager  
from datetime import datetime
from uuid import UUID, uuid4
from fastapi import UploadFile, HTTPException
from fastapi.responses import FileResponse
import os
import logging
from src.config import Config

class StorageService:
    # Storage limit in bytes (400MB)
    MAX_STORAGE_BYTES = 400 * 1024 * 1024
    
    async def get_user_storage_usage(self, user_id: UUID, session: AsyncSession) -> int:
        """Calculate the total storage usage for a user in bytes."""
        statement = select(func.sum(FileModel.size)).where(FileModel.user_id == user_id)
        result = await session.execute(statement)
        total_size = result.scalar_one_or_none()
        return total_size or 0  # Return 0 if no files found
    
    async def check_storage_limit(self, user_id: UUID, file_size: int, session: AsyncSession) -> bool:
        """Check if uploading a file would exceed the user's storage limit."""
        current_usage = await self.get_user_storage_usage(user_id, session)
        return (current_usage + file_size) > self.MAX_STORAGE_BYTES
    
    async def list_files(self, user_id: UUID, session: AsyncSession):
        """List all files for a specific user."""
        try:
            statement = select(FileModel).where(FileModel.user_id == user_id).order_by(desc(FileModel.created_at))
            result = await session.execute(statement)
            files = result.scalars().all()
            return files
        except Exception as e:
            return []

    async def get_file(self, file_uuid: UUID, user_id: UUID, session: AsyncSession):
        """Get file model by UUID, ensuring it belongs to the user."""
        statement = select(FileModel).where(
            (FileModel.uuid == file_uuid) & 
            (FileModel.user_id == user_id)
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_file_response(self, file_uuid: UUID, user_id: UUID, session: AsyncSession, preview = True):
        """Return a FileResponse from disk for a given file UUID."""
        file = await self.get_file(file_uuid, user_id, session)
        
        if not file:
            print("File not found in database")
            return None
        
        # Construct filename the same way as during upload
        storage_filename = f"{user_id}_{file.uuid}_{file.name}"
        # IMPORTANT: Apply the same sanitization as during upload
        sanitized_filename = self._sanitize_filename(storage_filename)
        
        print("Looking for file on disk:", sanitized_filename)
        
        if not DiskManager.file_exists(sanitized_filename):
            print("File exists in DB but not on disk:", file.name)
            return None
        
        # Use the sanitized filename to retrieve the file
        return DiskManager.get_file_response(sanitized_filename, file.name, preview)

    async def upload_file(self, file: UploadFile, folder_path: str, user_id: UUID, session: AsyncSession):
        """Upload file to disk and store metadata in DB with folder path."""
        # Stream to get file size instead of loading all at once
        file_size = 0
        chunk_size = 1024 * 1024  # 1MB chunks
        
        # Rewind file pointer to start
        await file.seek(0)
        
        # Check if filename already exists
        statement = select(FileModel).where(
            (FileModel.name == file.filename) & 
            (FileModel.folder_path == folder_path) &
            (FileModel.user_id == user_id)
        )
        result = await session.execute(statement)
        existing_file = result.scalar_one_or_none()
        
        if existing_file:
            # File already exists - return error
            raise HTTPException(
                status_code=409,
                detail=f"File '{file.filename}' already exists in folder '{folder_path}'"
            )
        
        try:
            # Create a temporary file to stream to
            import tempfile
            temp_file = tempfile.NamedTemporaryFile(delete=False)
            
            # Process file chunks
            chunk = await file.read(chunk_size)
            while chunk:
                file_size += len(chunk)
                temp_file.write(chunk)
                chunk = await file.read(chunk_size)
            
            temp_file.close()
            
            # Storage checks
            exceeds_limit = await self.check_storage_limit(user_id, file_size, session)
            if exceeds_limit:
                os.unlink(temp_file.name)
                current_usage = await self.get_user_storage_usage(user_id, session)
                current_usage_mb = current_usage / (1024 * 1024)
                max_storage_mb = self.MAX_STORAGE_BYTES / (1024 * 1024)
                raise HTTPException(
                    status_code=413,
                    detail=f"Storage limit exceeded. You have used {current_usage_mb:.2f}MB of your {max_storage_mb}MB limit."
                )
            
            # IMPORTANT: DO NOT use session.begin() here - it's already in a transaction
            new_file = FileModel(
                name=file.filename,
                folder_path=folder_path,
                size=file_size,
                user_id=user_id,
                created_at=datetime.now()
            )
            
            session.add(new_file)
            # CRITICAL: Add this explicit commit to ensure data is saved
            await session.commit()
            await session.refresh(new_file)
            
            # Now handle the physical file storage
            storage_filename = f"{user_id}_{new_file.uuid}_{file.filename}"
            sanitized_filename = self._sanitize_filename(storage_filename)
            
            # Copy from temp file to final location
            import shutil
            storage_path = os.path.join(Config.STORAGE_DIR, sanitized_filename)
            os.makedirs(os.path.dirname(storage_path), exist_ok=True)
            shutil.copy(temp_file.name, storage_path)
            
            # Clean up temp file
            os.unlink(temp_file.name)
            
            return new_file
        
        except Exception as e:
            # On error, roll back and clean up
            await session.rollback()
            if os.path.exists(temp_file.name):
                os.unlink(temp_file.name)
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal attacks."""
        # Replace potentially dangerous characters
        return "".join(c for c in filename if c.isalnum() or c in "._- ")

    async def delete_file(self, file_uuid: UUID, user_id: UUID, session: AsyncSession):
        """Delete the file from disk and DB."""
        file = await self.get_file(file_uuid, user_id, session)
        if not file:
            return None

        # Delete from disk using the sanitized storage filename
        storage_filename = f"{user_id}_{file.uuid}_{file.name}"
        sanitized_filename = self._sanitize_filename(storage_filename)
        DiskManager.delete_file(sanitized_filename)

        # Delete from DB
        await session.delete(file)
        await session.commit()

        return file

    async def explore_folder(self, folder_path: str, user_id: UUID, session: AsyncSession):
        """Explore a virtual folder and list its files and subfolders."""
        folder_path = folder_path.rstrip("/")
        
        # Special handling for root folder
        if not folder_path:  # Empty string means root folder
            # Get all files for this user
            stmt = select(FileModel).where(FileModel.user_id == user_id)
            result = await session.execute(stmt)
            all_files = result.scalars().all()
            
            # Extract top-level folders
            top_folders = set()
            root_files = []
            
            for file in all_files:
                parts = file.folder_path.strip("/").split("/")
                if parts and parts[0]:  # Non-empty first part
                    top_folders.add(parts[0])
                elif not file.folder_path:  # Files directly in root
                    root_files.append({
                        "type": "file",
                        "name": file.name,
                        "path": file.name,
                        "uuid": str(file.uuid),
                        "size": file.size,
                        "created_at": file.created_at.isoformat()
                    })
            
            folder_list = [{
                "type": "folder",
                "name": folder,
                "path": folder
            } for folder in sorted(top_folders)]
            
            # Sort files by name
            root_files = sorted(root_files, key=lambda x: x['name'].lower())
            
            return folder_list + root_files
        
        # Check if this folder exists by looking for ANY files in this folder
        # Use first() instead of scalar_one_or_none() to avoid multiple results error
        folder_check = select(FileModel).where(
            (FileModel.user_id == user_id) &
            (
                (FileModel.folder_path == folder_path) | 
                (FileModel.folder_path.like(f"{folder_path}/%"))
            )
        ).limit(1)  # Just need to check if any exist
        
        result = await session.execute(folder_check)
        first_item = result.first()
        folder_exists = first_item is not None
        
        # If folder doesn't exist, suggest similar folders
        if not folder_exists:
            # Get all unique folder paths for this user
            all_folders_stmt = select(FileModel.folder_path).where(
                FileModel.user_id == user_id
            ).distinct()
            result = await session.execute(all_folders_stmt)
            all_folder_paths = [row[0] for row in result.all()]
            
            # Find similar folders (e.g., "images" when user typed "image")
            similar_folders = []
            for path in all_folder_paths:
                if path and folder_path.lower() in path.lower():
                    # Just add the top-level folder
                    top_folder = path.split('/')[0] if '/' in path else path
                    if top_folder and top_folder not in similar_folders:
                        similar_folders.append(top_folder)
            
            if similar_folders:
                # Return a helpful error with suggestions
                raise HTTPException(
                    status_code=404,
                    detail={
                        "message": f"Folder '{folder_path}' not found",
                        "suggestions": similar_folders
                    }
                )
            else:
                # No similar folders found
                raise HTTPException(
                    status_code=404, 
                    detail=f"Folder '{folder_path}' not found"
                )
        
        # Get files in this folder and immediate subfolders
        stmt = select(FileModel).where(
            (FileModel.user_id == user_id) &
            (
                # Exact folder match OR immediate child folder
                (FileModel.folder_path == folder_path) | 
                (FileModel.folder_path.startswith(f"{folder_path}/"))
            )
        )

        result = await session.execute(stmt)
        all_items = result.scalars().all()

        files = []
        folders = set()

        for item in all_items:
            if item.folder_path == folder_path:
                # This file is in the current folder
                files.append({
                    "type": "file",
                    "name": item.name,
                    "path": os.path.join(item.folder_path, item.name),
                    "uuid": str(item.uuid),
                    "size": item.size,
                    "created_at": item.created_at.isoformat()
                })
            else:
                # This file is in a subfolder
                # Extract the next level folder name only
                rel_path = item.folder_path[len(folder_path):].strip("/")
                if "/" in rel_path:
                    subfolder = rel_path.split("/")[0]
                    folders.add(subfolder)
                else:
                    folders.add(rel_path)

        folder_list = [{
            "type": "folder",
            "name": folder,
            "path": os.path.join(folder_path, folder)
        } for folder in sorted(folders)]

        files = sorted(files, key=lambda x: x['name'].lower())
        return folder_list + files

    async def delete_folder(self, folder_path: str, user_id: UUID, session: AsyncSession):
        """Delete all files in a folder and the folder itself including subfolders."""
        try:
            # Get all files in the folder AND its subfolders
            stmt = select(FileModel).where(
                (FileModel.user_id == user_id) &
                (
                    # Exact folder match OR any subfolder (using LIKE)
                    (FileModel.folder_path == folder_path) | 
                    (FileModel.folder_path.like(f"{folder_path}/%"))
                )
            )
            result = await session.execute(stmt)
            files = result.scalars().all()

            if not files:
                raise HTTPException(status_code=404, detail="Folder not found or empty")

            
            # Delete all files one by one
            deleted_count = 0
            for file in files:
                try:
                    # Delete from disk first
                    storage_filename = f"{user_id}_{file.uuid}_{file.name}"
                    sanitized_filename = self._sanitize_filename(storage_filename)
                    DiskManager.delete_file(sanitized_filename)
                    
                    # Then delete from DB
                    await session.delete(file)
                    deleted_count += 1
                except Exception as e:
                    logging.error(f"Error deleting file {file.uuid}: {str(e)}")
            
            # Commit after all deletions
            try:
                await session.commit()
            except Exception as e:
                logging.error(f"Failed to commit deletion transaction: {str(e)}")
                await session.rollback()
                raise HTTPException(
                    status_code=500,
                    detail="Failed to delete folder contents from database"
                )
                    
            return {"message": f"Folder and its contents deleted successfully ({deleted_count} files)"}
                
        except HTTPException:
            # Pass through HTTP exceptions
            raise
        except Exception as e:
            logging.error(f"Failed to delete folder {folder_path}: {str(e)}")
            # Try to rollback if possible
            try:
                await session.rollback()
            except:
                pass
            raise HTTPException(
                status_code=500,
                detail="An error occurred while deleting the folder"
            )