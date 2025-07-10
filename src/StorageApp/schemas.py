from pydantic import BaseModel, Field
import uuid
from datetime import datetime

class FileSchema(BaseModel):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, description="Unique identifier for the file")
    name: str = Field(..., description="Name of the file")
    size: int = Field(..., description="Size of the file in bytes")
    created_at: datetime
    parent_path: str
    class Config:
        orm_mode = True
        schema_extra = {
            "example": {
                "name": "example.txt",
                "size": 1024,
            }
        }


class FileUploadSchema(BaseModel):
    file: bytes = Field(..., description="File content in bytes")
    name: str = Field(..., description="Name of the file to be uploaded")
    parent_path: str = Field(..., description="Path where the file will be stored")

    class Config:
        schema_extra = {
            "example": {
                "file": "base64_encoded_file_content",
                "name": "example.txt",
                "parent_folder": "/storage"
            }
        }