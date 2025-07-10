import os
import mimetypes
from fastapi.responses import FileResponse
from uuid import UUID

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")


class Disk_Manager:
    @staticmethod
    def get_file_path(file_name: str) -> str:
        """
        Get the full path of a file in the storage directory.
        """
        return os.path.join(STORAGE_DIR, file_name)

    @staticmethod
    def file_exists(file_name: str) -> bool:
        """
        Check if a file exists in the storage directory.
        """
        return os.path.exists(Disk_Manager.get_file_path(file_name))

    @staticmethod
    def get_file_response(file_name: str) -> FileResponse:
        """
        Get a FileResponse for a file in the storage directory.
        """
        file_path = Disk_Manager.get_file_path(file_name)
        media_type = mimetypes.guess_type(file_name)[0] or 'application/octet-stream'
        return FileResponse(file_path, media_type=media_type, filename=file_name)
    

    @staticmethod
    def delete_file(file_name: str) -> bool:
        """
        Delete a file from the storage directory.
        Returns True if the file was deleted, False if it did not exist.
        """
        file_path = Disk_Manager.get_file_path(file_name)
        if os.path.exists(file_path):
            os.remove(file_path)
            return True
        return False
    
    @staticmethod
    def save_file(file_name: str, content: bytes) -> str:
        """
        Save file content to disk.
        Returns the full path of the saved file.
        """
        os.makedirs(STORAGE_DIR, exist_ok=True)
        file_path = Disk_Manager.get_file_path(file_name)
        with open(file_path, "wb") as f:
            f.write(content)
        return file_path
    

DiskManager = Disk_Manager()  # Alias for easier reference