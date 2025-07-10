from fastapi import APIRouter,status,Depends
from fastapi import UploadFile, File
from typing import *
from fastapi.responses import JSONResponse,FileResponse
from fastapi.exceptions import HTTPException
from src.StorageApp.files import files
from src.StorageApp.schemas import FileSchema,FileUploadSchema
from dotenv import load_dotenv
import os
import mimetypes
from datetime import datetime
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


@storage_router.get("/get_file/{file_uuid}",status_code=status.HTTP_200_OK)
async def get_file(file_uuid: UUID, session: AsyncSession = Depends(get_session)):
    file = await service.get_file( file_uuid,session )
    if file is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return FileResponse(
        os.path.join(STORAGE_DIR, file.name),
        media_type=mimetypes.guess_type(file.name)[0] or 'application/octet-stream',
        filename=file.name
    )

@storage_router.post("/upload_file", status_code=status.HTTP_201_CREATED)
async def upload_file(file: UploadFile = File(...), session: AsyncSession = Depends(get_session)):
    """
    Upload a file to the storage.
    """
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File name is required")
    
    # Create directory if it doesn't exist
    os.makedirs(STORAGE_DIR, exist_ok=True)
    
    file_content = await file.read()
    file_upload = FileUploadSchema(
        name=file.filename,
        parent_path="",
        file=file_content
    )
    
    new_file = await service.upload_file(file_upload, session)
    
    # Save the file to the storage directory
    file_path = os.path.join(STORAGE_DIR, new_file.name)
    with open(file_path, 'wb') as f:
        f.write(file_content)

    # Convert UUID to string for JSON serialization
    response_data = {
        "uuid": str(new_file.uuid),
        "name": new_file.name,
        "folder_path": new_file.folder_path,
        "size": new_file.size,
        "created_at": new_file.created_at.isoformat()
    }

    return JSONResponse(content=response_data, status_code=status.HTTP_201_CREATED)
