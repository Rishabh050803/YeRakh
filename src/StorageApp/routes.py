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
    """
    List all files in the storage for the authenticated user.
    
    This endpoint retrieves all files owned by the current user, regardless of folder structure.
    Files are sorted by creation date (newest first).
    
    Authorization:
        Requires a valid JWT access token.
    
    Returns:
        JSONResponse: A 200 OK response with an array of file objects containing:
            - uuid: Unique identifier for the file
            - name: Original filename
            - folder_path: Virtual folder path where the file is stored
            - size: File size in bytes
            - created_at: ISO-formatted creation timestamp
    
    Example:
        GET /storage/list_files
    """
     
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
    """
    Retrieve a specific file by its UUID.
    
    This endpoint allows downloading or previewing a file from the user's storage.
    
    Path Parameters:
        file_uuid (UUID): The unique identifier of the file to retrieve.
    
    Query Parameters:
        preview (bool, optional): If True, attempts to display the file in the browser.
                                  If False, forces download. Default is False.
    
    Authorization:
        Requires a valid JWT access token.
        User can only access their own files.
    
    Returns:
        FileResponse: The file with appropriate content-type and disposition headers.
    
    Raises:
        HTTPException (404): If the file doesn't exist or doesn't belong to the user.
    
    Example:
        GET /storage/get_file/3d8fbb26-73d3-4898-93cf-385f4ec59210
        GET /storage/get_file/3d8fbb26-73d3-4898-93cf-385f4ec59210?preview=true
    """

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
    """
    Upload a file to the user's storage with an optional folder path.
    
    This endpoint handles file uploads, storage quota validation, and metadata recording.
    
    Form Data:
        file (UploadFile): The file to upload.
        folder_path (str, optional): Virtual folder path to store the file. 
                                     Defaults to root folder ("").
    
    Authorization:
        Requires a valid JWT access token.
    
    Returns:
        JSON: A 201 Created response with details of the uploaded file:
            - uuid: Unique identifier for the file
            - name: Original filename
            - folder_path: Virtual folder path where the file is stored
            - size: File size in bytes
            - created_at: ISO-formatted creation timestamp
            - storage_usage: Object containing storage metrics:
                - used_mb: Current storage usage in MB
                - total_mb: Total storage quota in MB
                - percentage: Percentage of quota used
    
    Raises:
        HTTPException (400): If the filename is missing
        HTTPException (413): If the upload would exceed the user's storage quota
        HTTPException (409): If a file with the same name already exists in that folder
    
    Example:
        POST /storage/upload_file
        (with multipart form data containing file and optional folder_path)
    """

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
    """
    Delete a specific file by its UUID.
    
    This endpoint removes a file from both storage and database records.
    
    Path Parameters:
        file_uuid (UUID): The unique identifier of the file to delete.
    
    Authorization:
        Requires a valid JWT access token.
        User can only delete their own files.
    
    Returns:
        JSON: A 200 OK response with a success message and updated storage usage:
            - message: Confirmation message
            - storage_usage: Object containing storage metrics:
                - used_mb: Current storage usage in MB
                - total_mb: Total storage quota in MB
                - percentage: Percentage of quota used
    
    Raises:
        HTTPException (404): If the file doesn't exist or doesn't belong to the user.
    
    Example:
        DELETE /storage/delete_file/3d8fbb26-73d3-4898-93cf-385f4ec59210
    """

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
    """
    Explore a virtual folder and list its files and subfolders.
    
    This endpoint provides a hierarchical view of the user's storage structure.
    When exploring the root folder (empty path), it shows all top-level folders and files.
    
    Path Parameters:
        folder_path (str): URL-encoded path of the folder to explore.
                           Use empty string for root folder.
    
    Authorization:
        Requires a valid JWT access token.
    
    Returns:
        JSONResponse: A 200 OK response with an array of items:
            - For folders:
                - type: "folder"
                - name: Folder name
                - path: Full path to the folder
            - For files:
                - type: "file"
                - name: Filename
                - path: Full path to the file
                - uuid: Unique identifier for the file
                - size: File size in bytes
                - created_at: ISO-formatted creation timestamp
            
            Returns an empty array if the folder exists but has no contents.
    
    Raises:
        HTTPException (404): If the folder doesn't exist. May include suggestions for similar folders.
    
    Example:
        GET /storage/explore_folder/
        GET /storage/explore_folder/images
        GET /storage/explore_folder/documents/reports
    """
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
    """
    Delete a virtual folder and all its contents recursively.
    
    This endpoint removes all files within a folder and its subfolders.
    It deletes both the database records and the physical files.
    
    Path Parameters:
        folder_path (str): URL-encoded path of the folder to delete.
    
    Authorization:
        Requires a valid JWT access token.
        User can only delete their own folders.
    
    Returns:
        JSON: A 200 OK response with a success message and updated storage usage:
            - message: Confirmation message with details on deleted items
            - storage_usage: Object containing storage metrics:
                - used_mb: Current storage usage in MB
                - total_mb: Total storage quota in MB
                - percentage: Percentage of quota used
    
    Raises:
        HTTPException (404): If the folder doesn't exist or is empty.
        HTTPException (500): If there's an error during the deletion process.
    
    Example:
        DELETE /storage/delete_folder/images
        DELETE /storage/delete_folder/documents/reports
    """
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
    """
    Get the current storage usage statistics for the authenticated user.
    
    This endpoint provides a summary of the user's storage quota and usage.
    
    Authorization:
        Requires a valid JWT access token.
    
    Returns:
        JSON: A 200 OK response with storage metrics:
            - storage_usage:
                - used_mb: Current storage usage in MB
                - total_mb: Total storage quota in MB (400MB)
                - percentage: Percentage of quota used
    
    Example:
        GET /storage/storage_usage
    """
    current_usage = await service.get_user_storage_usage(current_user.uid, session)
    current_usage_mb = current_usage / (1024 * 1024)
    
    return {
        "storage_usage": {
            "used_mb": round(current_usage_mb, 2),
            "total_mb": 400,
            "percentage": round((current_usage_mb / 400) * 100, 2)
        }
    }