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
import structlog

# Replace all print statements with structured logging
logger = structlog.get_logger()


class StorageService:
    # Storage limit in bytes (400MB)
    MAX_STORAGE_BYTES = 400 * 1024 * 1024

    async def get_user_storage_usage(self, user_id: UUID, session: AsyncSession) -> int:
        """Calculate the total storage usage for a user in bytes."""
        statement = select(func.sum(FileModel.size)).where(FileModel.user_id == user_id)
        result = await session.execute(statement)
        total_size = result.scalar_one_or_none()
        return total_size or 0  # Return 0 if no files found

    async def check_storage_limit(
        self, user_id: UUID, file_size: int, session: AsyncSession
    ) -> bool:
        """Check if uploading a file would exceed the user's storage limit."""
        current_usage = await self.get_user_storage_usage(user_id, session)
        return (current_usage + file_size) > self.MAX_STORAGE_BYTES

    async def list_files(self, user_id: UUID, session: AsyncSession):
        """List all files for a specific user."""
        try:
            statement = (
                select(FileModel)
                .where(FileModel.user_id == user_id)
                .order_by(desc(FileModel.created_at))
            )
            result = await session.execute(statement)
            files = result.scalars().all()
            return files
        except Exception as e:
            return []

    async def get_file(self, file_uuid: UUID, user_id: UUID, session: AsyncSession):
        """Get file model by UUID, ensuring it belongs to the user."""
        statement = select(FileModel).where(
            (FileModel.uuid == file_uuid) & (FileModel.user_id == user_id)
        )
        result = await session.execute(statement)
        return result.scalar_one_or_none()

    async def get_file_response(
        self, file_uuid: UUID, user_id: UUID, session: AsyncSession, preview=True
    ):
        """Return a FileResponse from disk for a given file UUID."""
        file = await self.get_file(file_uuid, user_id, session)

        if not file:
            logger.error("File not found in database", file_uuid=str(file_uuid), user_id=str(user_id))
            return None

        blob_name = self._get_storage_path(user_id=user_id, file_uuid=file.uuid,file_name=file.name)

        return DiskManager.generate_signed_url_with_retry(
            os.getenv("GCS_BUCKET_NAME"),
            blob_name,
            expiration_minutes=5,
        )

    async def upload_file(
        self,
        file_name: str,
        folder_path: str,
        file_size: int,
        user_id: UUID,
        session: AsyncSession,
        content_type: str = None,
        client_origin: str = None,  # Add parameter for client origin
    ):
        """Upload file to disk and store metadata in DB with folder path."""
        # Stream to get file size instead of loading all at once

        # Check if filename already exists
        statement = select(FileModel).where(
            (FileModel.name == file_name)
            & (FileModel.folder_path == folder_path)
            & (FileModel.user_id == user_id)
        )
        result = await session.execute(statement)
        existing_file = result.scalar_one_or_none()

        if existing_file:
            # File already exists - return error
            raise HTTPException(
                status_code=409,
                detail=f"File '{file_name}' already exists in folder '{folder_path}'",
            )

        try:
            # Storage checks
            exceeds_limit = await self.check_storage_limit(user_id, file_size, session)
            if exceeds_limit:
                current_usage = await self.get_user_storage_usage(user_id, session)
                current_usage_mb = current_usage / (1024 * 1024)
                max_storage_mb = self.MAX_STORAGE_BYTES / (1024 * 1024)
                raise HTTPException(
                    status_code=413,
                    detail=f"Storage limit exceeded. You have used {current_usage_mb:.2f}MB of your {max_storage_mb}MB limit.",
                )

            # IMPORTANT: DO NOT use session.begin() here - it's already in a transaction
            new_file = FileModel(
                name=file_name,
                folder_path=folder_path,
                size=file_size,
                user_id=user_id,
                created_at=datetime.now(),
                confirmation=False,
            )

            session.add(new_file)
            # CRITICAL: Add this explicit commit to ensure data is saved
            await session.commit()
            await session.refresh(new_file)

            blob_name = self._get_storage_path(user_id=user_id, file_uuid=new_file.uuid,file_name=new_file.name)
            bucket_name = os.getenv("GCS_BUCKET_NAME")
            
            # Generate both types of upload URLs
            direct_url = DiskManager.generate_signed_upload_url(
                bucket_name=bucket_name,
                blob_name=blob_name,
                expiration=5,
                content_type=content_type,
                origin=client_origin,  # Pass client origin for CORS headers
            )
            
            # Generate resumable upload URL
            resumable_url = DiskManager.generate_resumable_upload_url(
                bucket_name=bucket_name,
                blob_name=blob_name,
                expiration=5,
                content_type=content_type,
                origin=client_origin,  # Pass client origin for CORS headers
            )
            
            return {
                "file_id": str(new_file.uuid),
                "upload_url": direct_url,  # For backward compatibility
                "resumable_url": resumable_url,  # New resumable upload URL
                "client_origin": client_origin,  # Echo back the client origin for frontend use
            }

        except Exception as e:
            # On error, roll back and clean up
            await session.rollback()
            if os.path.exists(file_name):
                os.unlink(file_name)
            raise HTTPException(status_code=500, detail=f"File upload failed: {str(e)}")

    async def confirm_file_upload(
        self, file_uuid: UUID, user_id: UUID, session: AsyncSession
    ):
        """Confirm a file upload by setting the confirmation flag."""
        try:
            file = await self.get_file(file_uuid, user_id, session)
            if not file:
                raise HTTPException(status_code=404, detail="File not found")

            file.confirmation = True
            await session.commit()
            return True
        except Exception as e:
            await session.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to confirm file: {str(e)}")

    def _sanitize_filename(self, filename: str) -> str:
        """Sanitize filename to prevent path traversal attacks."""
        # Replace potentially dangerous characters
        return "".join(c for c in filename if c.isalnum() or c in "._- ")

    def _get_storage_path(self, user_id: UUID, file_uuid: UUID, file_name: str = None) -> str:
        """Generate consistent GCS path for a file."""
        if file_name:
            base_name = f"{user_id}_{file_uuid}_{file_name}"
            sanitized = self._sanitize_filename(base_name)
            return f"{user_id}/{sanitized}"
        else:
            # For operations that don't need the filename
            return f"{user_id}/{user_id}_{file_uuid}"
    

    async def delete_file(self, file_uuid: UUID, user_id: UUID, session: AsyncSession):
        """Delete file with better transaction handling."""
        file = await self.get_file(file_uuid, user_id, session)
        if not file:
            return None

        # Get GCS path
        
        blob_name = self._get_storage_path(user_id=user_id, file_uuid=file.uuid,file_name=file.name)
        
        # First try to delete from GCS
        gcs_result = DiskManager.delete_blob(
            bucket_name=os.getenv("GCS_BUCKET_NAME"),
            blob_name=blob_name
        )
        
        if gcs_result:
            # If GCS delete succeeds, delete from DB
            
            await session.delete(file)
            await session.commit()
            return True
        else:
            # If GCS delete fails, log but don't delete from DB to maintain consistency
            logging.error(f"Failed to delete file {file_uuid} from storage, DB record kept")
            return False

    async def explore_folder(
        self, folder_path: str, user_id: UUID, session: AsyncSession
    ):
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
                    root_files.append(
                        {
                            "type": "file",
                            "name": file.name,
                            "path": file.name,
                            "uuid": str(file.uuid),
                            "size": file.size,
                            "created_at": file.created_at.isoformat(),
                        }
                    )

            folder_list = [
                {"type": "folder", "name": folder, "path": folder}
                for folder in sorted(top_folders)
            ]

            # Sort files by name
            root_files = sorted(root_files, key=lambda x: x["name"].lower())

            return folder_list + root_files

        # Check if this folder exists by looking for ANY files in this folder
        # Use first() instead of scalar_one_or_none() to avoid multiple results error
        folder_check = (
            select(FileModel)
            .where(
                (FileModel.user_id == user_id)
                & (
                    (FileModel.folder_path == folder_path)
                    | (FileModel.folder_path.like(f"{folder_path}/%"))
                )
            )
            .limit(1)
        )  # Just need to check if any exist

        result = await session.execute(folder_check)
        first_item = result.first()
        folder_exists = first_item is not None

        # If folder doesn't exist, suggest similar folders
        if not folder_exists:
            # Get all unique folder paths for this user
            all_folders_stmt = (
                select(FileModel.folder_path)
                .where(FileModel.user_id == user_id)
                .distinct()
            )
            result = await session.execute(all_folders_stmt)
            all_folder_paths = [row[0] for row in result.all()]

            # Find similar folders (e.g., "images" when user typed "image")
            similar_folders = []
            for path in all_folder_paths:
                if path and folder_path.lower() in path.lower():
                    # Just add the top-level folder
                    top_folder = path.split("/")[0] if "/" in path else path
                    if top_folder and top_folder not in similar_folders:
                        similar_folders.append(top_folder)

            if similar_folders:
                # Return a helpful error with suggestions
                raise HTTPException(
                    status_code=404,
                    detail={
                        "message": f"Folder '{folder_path}' not found",
                        "suggestions": similar_folders,
                    },
                )
            else:
                # No similar folders found
                raise HTTPException(
                    status_code=404, detail=f"Folder '{folder_path}' not found"
                )

        # Get files in this folder and immediate subfolders
        stmt = select(FileModel).where(
            (FileModel.user_id == user_id)
            & (
                # Exact folder match OR immediate child folder
                (FileModel.folder_path == folder_path)
                | (FileModel.folder_path.startswith(f"{folder_path}/"))
            )
        )

        result = await session.execute(stmt)
        all_items = result.scalars().all()

        files = []
        folders = set()

        for item in all_items:
            if item.folder_path == folder_path:
                # This file is in the current folder
                files.append(
                    {
                        "type": "file",
                        "name": item.name,
                        "path": os.path.join(item.folder_path, item.name),
                        "uuid": str(item.uuid),
                        "size": item.size,
                        "created_at": item.created_at.isoformat(),
                    }
                )
            else:
                # This file is in a subfolder
                # Extract the next level folder name only
                rel_path = item.folder_path[len(folder_path) :].strip("/")
                if "/" in rel_path:
                    subfolder = rel_path.split("/")[0]
                    folders.add(subfolder)
                else:
                    folders.add(rel_path)

        folder_list = [
            {
                "type": "folder",
                "name": folder,
                "path": os.path.join(folder_path, folder),
            }
            for folder in sorted(folders)
        ]

        files = sorted(files, key=lambda x: x["name"].lower())
        return folder_list + files

    async def delete_folder(
        self, folder_path: str, user_id: UUID, session: AsyncSession
    ):
        """Delete all files in a folder and the folder itself including subfolders."""
        try:
            # Get all files in the folder AND its subfolders
            stmt = select(FileModel).where(
                (FileModel.user_id == user_id)
                & (
                    # Exact folder match OR any subfolder (using LIKE)
                    (FileModel.folder_path == folder_path)
                    | (FileModel.folder_path.like(f"{folder_path}/%"))
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
                    # First delete from GCS
                    blob_name = self._get_storage_path(user_id=user_id, file_uuid=file.uuid, file_name=file.name)
                    gcs_result = DiskManager.delete_blob(
                        bucket_name=os.getenv("GCS_BUCKET_NAME"),
                        blob_name=blob_name
                    )
                    # Only delete from DB if GCS delete was successful
                    if gcs_result:
                        await session.delete(file)
                        deleted_count += 1
                    else:
                        logging.error(f"Failed to delete file {file.uuid} from GCS, skipping DB deletion")
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
                    detail="Failed to delete folder contents from database",
                )

            return {
                "message": f"Folder and its contents deleted successfully ({deleted_count} files)"
            }

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
                status_code=500, detail="An error occurred while deleting the folder"
            )

    async def cleanup_unconfirmed_uploads(self, max_age_hours: int = 24, session: AsyncSession = None):
        """Clean up unconfirmed uploads older than the specified age."""
        try:
            # Create a session if none provided
            if session is None:
                from DB.main import get_session
                async with get_session() as session:
                    return await self._perform_cleanup(max_age_hours, session)
            else:
                return await self._perform_cleanup(max_age_hours, session)
        except Exception as e:
            logging.error(f"Failed to clean up unconfirmed uploads: {str(e)}")
            return {"status": "error", "message": str(e)}

    async def _perform_cleanup(self, max_age_hours: int, session: AsyncSession):
        # Find unconfirmed files older than threshold
        cutoff_time = datetime.now() - datetime.timedelta(hours=max_age_hours)
        stmt = select(FileModel).where(
            (FileModel.confirmation == False) & 
            (FileModel.created_at < cutoff_time)
        )
        result = await session.execute(stmt)
        files = result.scalars().all()
        
        if not files:
            return {"status": "success", "message": "No unconfirmed uploads to clean up"}
        
        # Delete files from GCS and database
        deleted_count = 0
        for file in files:
            try:
                blob_name = self._get_storage_path(
                    user_id=file.user_id, 
                    file_uuid=file.uuid, 
                    file_name=file.name
                )
                
                # Try to delete from GCS if it exists
                if DiskManager.blob_exists(os.getenv("GCS_BUCKET_NAME"), blob_name):
                    DiskManager.delete_blob(os.getenv("GCS_BUCKET_NAME"), blob_name)
                
                # Delete from database
                await session.delete(file)
                deleted_count += 1
            except Exception as e:
                logging.error(f"Error cleaning up file {file.uuid}: {str(e)}")
    
        # Commit changes
        await session.commit()
        
        return {
            "status": "success", 
            "message": f"Cleaned up {deleted_count} unconfirmed uploads"
        }


