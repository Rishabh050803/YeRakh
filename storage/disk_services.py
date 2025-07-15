import os
import mimetypes
from fastapi.responses import FileResponse

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")

class DiskManager:
    @staticmethod
    def save_file(filename: str, content: bytes):
        """Save file content to disk."""
        os.makedirs(STORAGE_DIR, exist_ok=True)
        file_path = os.path.join(STORAGE_DIR, filename)
        
        with open(file_path, "wb") as f:
            f.write(content)
        
        return file_path
        
    @staticmethod
    def file_exists(filename: str) -> bool:
        """Check if a file exists on disk."""
        file_path = os.path.join(STORAGE_DIR, filename)
        return os.path.exists(file_path)
        
    @staticmethod
    def get_file_response(storage_filename: str, original_filename: str, preview=False):
        """Return a FileResponse for downloading or previewing a file."""
        file_path = os.path.join(STORAGE_DIR, storage_filename)
        
        if not os.path.exists(file_path):
            return None
            
        # Guess the content type
        content_type, _ = mimetypes.guess_type(original_filename)
        
        # Set disposition based on request type
        disposition = "inline" if preview else "attachment"
        
        return FileResponse(
            path=file_path,
            filename=original_filename,
            media_type=content_type,
            content_disposition_type=disposition
        )
        
    @staticmethod
    def delete_file(filename: str):
        """Delete a file from disk."""
        file_path = os.path.join(STORAGE_DIR, filename)
        
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                return True
            else:
                print(f"Warning: File {filename} not found on disk")
                return False
        except Exception as e:
            print(f"Error deleting file {filename}: {str(e)}")
            return False