from fastapi import APIRouter, status, Depends, UploadFile, File, Form
from typing import *
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import HTTPException
import os
import urllib.parse
from .services import *
from DB.main import get_session
from src.Auth.dependencies import get_current_user
from src.Auth.models import User

storage_router = APIRouter()    
service = StorageService()

@storage_router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """Health check endpoint to verify if the service is running."""
    return JSONResponse(content={"status": "ok"}, status_code=status.HTTP_200_OK)

@storage_router.get("/list_files", status_code=status.HTTP_200_OK)
async def list_files(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """List all files in the storage for the current user."""
    files = await service.list_files(current_user.uid, session)
    
    # Convert each file to a dictionary with serializable values
    response_data = [
        {
            "uuid": str(file.uuid),
            "name": file.name,
            "folder_path": file.folder_path,
            "size": file.size,
            "created_at": file.created_at.isoformat()
        }
        for file in files
    ]
    
    return JSONResponse(content=response_data, status_code=status.HTTP_200_OK)

@storage_router.get("/get_file/{file_uuid}", status_code=status.HTTP_200_OK)
async def get_file(
    file_uuid: UUID,
    preview: bool = False,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Endpoint to retrieve a specific file by UUID."""
    response = await service.get_file_response(file_uuid, current_user.uid, session, preview)
    if response is None:
        raise HTTPException(status_code=404, detail="File not found")
    return response

@storage_router.post("/upload_file", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    folder_path: str = Form(""),  # Default to root folder if not provided
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Upload a file to the storage with an optional folder path."""
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Get user's current storage usage
    current_usage = await service.get_user_storage_usage(current_user.uid, session)
    current_usage_mb = current_usage / (1024 * 1024)
    
    # Move all logic to the service
    new_file = await service.upload_file(file, folder_path, current_user.uid, session)

    # Calculate new storage usage
    new_usage = await service.get_user_storage_usage(current_user.uid, session)
    new_usage_mb = new_usage / (1024 * 1024)

    return {
        "uuid": str(new_file.uuid),
        "name": new_file.name,
        "folder_path": new_file.folder_path,
        "size": new_file.size,
        "created_at": new_file.created_at.isoformat(),
        "storage_usage": {
            "used_mb": round(new_usage_mb, 2),
            "total_mb": 400,
            "percentage": round((new_usage_mb / 400) * 100, 2)
        }
    }

@storage_router.delete("/delete_file/{file_uuid}", status_code=status.HTTP_200_OK)
async def delete_file(
    file_uuid: UUID, 
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    file = await service.delete_file(file_uuid, current_user.uid, session)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get updated storage usage
    current_usage = await service.get_user_storage_usage(current_user.uid, session)
    current_usage_mb = current_usage / (1024 * 1024)
    
    return {
        "message": "File deleted successfully",
        "storage_usage": {
            "used_mb": round(current_usage_mb, 2),
            "total_mb": 400,
            "percentage": round((current_usage_mb / 400) * 100, 2)
        }
    }

@storage_router.get("/explore_folder/{folder_path:path}", status_code=status.HTTP_200_OK)
async def explore_folder(
    folder_path: str, 
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Explore a virtual folder and list its files and subfolders."""
    # Decode URL-encoded paths (e.g., "my%20pics" -> "my pics")
    folder_path = urllib.parse.unquote(folder_path).rstrip("/")

    items = await service.explore_folder(folder_path, current_user.uid, session)

    if not items:
        # Return empty array instead of 404
        return JSONResponse(content=[], status_code=200)

    return JSONResponse(content=items, status_code=200)

@storage_router.delete("/delete_folder/{folder_path:path}", status_code=status.HTTP_200_OK)
async def delete_folder(
    folder_path: str, 
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Delete a virtual folder and all its contents."""
    # Decode URL-encoded paths (e.g., "my%20pics" -> "my pics")
    folder_path = urllib.parse.unquote(folder_path).rstrip("/")

    result = await service.delete_folder(folder_path, current_user.uid, session)
    
    # Get updated storage usage
    current_usage = await service.get_user_storage_usage(current_user.uid, session)
    current_usage_mb = current_usage / (1024 * 1024)
    
    return {
        "message": result["message"],
        "storage_usage": {
            "used_mb": round(current_usage_mb, 2),
            "total_mb": 400,
            "percentage": round((current_usage_mb / 400) * 100, 2)
        }
    }

@storage_router.get("/storage_usage", status_code=status.HTTP_200_OK)
async def get_storage_usage(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Get the current storage usage for the user."""
    current_usage = await service.get_user_storage_usage(current_user.uid, session)
    current_usage_mb = current_usage / (1024 * 1024)
    
    return {
        "storage_usage": {
            "used_mb": round(current_usage_mb, 2),
            "total_mb": 400,
            "percentage": round((current_usage_mb / 400) * 100, 2)
        }
    }