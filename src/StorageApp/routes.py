from fastapi import APIRouter,status,Depends
from fastapi import APIRouter, status, Depends, UploadFile, File, Form
from typing import *
from fastapi.responses import JSONResponse,FileResponse
from fastapi.exceptions import HTTPException
import os
import urllib.parse
from .services import *
from DB.main import get_session

storage_router = APIRouter()    

service = StorageService()
STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")


@storage_router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint to verify if the service is running.
    """
    return JSONResponse(content={"status": "ok"}, status_code=status.HTTP_200_OK)


@storage_router.get("/list_files", status_code=status.HTTP_200_OK)
async def list_files(session: AsyncSession = Depends(get_session)):
    """
    List all files in the storage.
    """
    files = await service.list_files(session)
    
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
async def get_file(file_uuid: UUID, session: AsyncSession = Depends(get_session)):
    """
    Endpoint to retrieve a specific file by UUID.
    """
    response = await service.get_file_response(file_uuid, session)
    if response is None:
        raise HTTPException(status_code=404, detail="File not found")
    return response


@storage_router.post("/upload_file", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file: UploadFile = File(...),
    folder_path: str = Form(""),  # Default to root folder if not provided
    session: AsyncSession = Depends(get_session)
):
    """
    Upload a file to the storage with an optional folder path.
    The folder path is virtual and used for organization only.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Move all logic to the service
    new_file = await service.upload_file(file, folder_path, session)

    return {
        "uuid": str(new_file.uuid),
        "name": new_file.name,
        "folder_path": new_file.folder_path,
        "size": new_file.size,
        "created_at": new_file.created_at.isoformat()
    }


@storage_router.delete("/delete_file/{file_uuid}", status_code=status.HTTP_200_OK)
async def delete_file(file_uuid: UUID, session: AsyncSession = Depends(get_session)):
    file = await service.delete_file(file_uuid, session)
    if file is None:
        raise HTTPException(status_code=404, detail="File not found")
    return {"message": "File deleted successfully"}


@storage_router.get("/explore_folder/{folder_path:path}", status_code=status.HTTP_200_OK)
async def explore_folder(folder_path: str, session: AsyncSession = Depends(get_session)):
    """
    Explore a virtual folder and list its files and subfolders.
    """
    # Decode URL-encoded paths (e.g., "my%20pics" -> "my pics")
    print("folder_path", folder_path)
    folder_path = urllib.parse.unquote(folder_path).rstrip("/")

    items = await service.explore_folder(folder_path, session)

    if not items:
        raise HTTPException(status_code=404, detail="Folder not found or empty")

    return JSONResponse(content=items, status_code=200)

@storage_router.delete("/delete_folder/{folder_path:path}", status_code=status.HTTP_200_OK)
async def delete_folder(folder_path: str, session: AsyncSession = Depends(get_session)):
    """
    Delete a virtual folder and all its contents.
    """
    # Decode URL-encoded paths (e.g., "my%20pics" -> "my pics")
    folder_path = urllib.parse.unquote(folder_path).rstrip("/")

    deleted_count = await service.delete_folder(folder_path, session)

    if deleted_count == 0:
        raise HTTPException(status_code=404, detail="Folder not found or empty")

    return {"message": f"Deleted {deleted_count} items from folder '{folder_path}'"}