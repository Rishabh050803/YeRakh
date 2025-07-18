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
from google.cloud import storage

storage_router = APIRouter()    
service = StorageService()

@storage_router.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint to verify if the service is running.
    
    Implementation Details:
    - Simple health probe that returns static JSON response
    - Used by load balancers and monitoring systems to check API availability
    - Does NOT check database or GCS connectivity (see /storage-status for that)
    - Fast response time (<10ms) for minimal overhead
    
    Response Structure:
    - JSON object with "status": "ok"
    - HTTP 200 OK status code
    
    Usage Context:
    - Called frequently by infrastructure
    - Should never fail unless service is completely down
    """
    return JSONResponse(content={"status": "ok"}, status_code=status.HTTP_200_OK)

@storage_router.get("/storage-status")
async def check_storage_status():
    """
    Check if GCS storage service is accessible and properly configured.
    
    Implementation Details:
    - Tests actual connection to configured GCS bucket
    - Uses DiskManager.check_gcs_connection() which lists a single blob
    - Verifies credentials, permissions, and network connectivity
    - NOT cached - performs real-time check on each call
    
    Response Structure:
    - Success: {"status": "ok", "provider": "Google Cloud Storage"}
    - Failure: {"status": "error", "message": "<error details>"}
    
    Error Handling:
    - Catches all exceptions from GCS client
    - Returns friendly error message instead of failing with 500
    - Common errors include invalid credentials, network issues, or missing bucket
    
    Usage Context:
    - Call during app initialization to verify storage setup
    - Useful for diagnosing storage connectivity issues
    - Consider periodic checks from monitoring systems
    """
    try:
        DiskManager.check_gcs_connection(os.getenv("GCS_BUCKET_NAME"))
        return {"status": "ok", "provider": "Google Cloud Storage"}
    except Exception as e:
        return {"status": "error", "message": str(e)}

@storage_router.get("/supported_content_types", status_code=status.HTTP_200_OK)
async def get_supported_content_types():
    """
    Retrieve the list of supported content types for file uploads.
    
    This endpoint returns a JSON array of MIME types that are allowed for file uploads.
    
    Returns:
        JSONResponse: A 200 OK response with an array of supported content types.
    
    Example:
        GET /storage/supported_content_types
    """
    content_types = [
        "image/jpeg", "image/png", "application/pdf",
        "text/plain", "application/msword","application/octet-stream",]
    
    return JSONResponse(content=content_types, status_code=status.HTTP_200_OK)

@storage_router.get("/list_files", status_code=status.HTTP_200_OK)
async def list_files(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    List all confirmed files owned by the authenticated user.
    
    Implementation Details:
    - Retrieves only confirmed files (confirmation=True)
    - Sorts by created_at timestamp in descending order (newest first)
    - Returns files from all folders in a flat structure
    - All fields are serialized to JSON-compatible formats
    - UUID converted to string for JSON compatibility
    - Timestamps converted to ISO-8601 format
    
    Database Flow:
    1. Query FileModel for all files with user_id matching current user
    2. Order by created_at DESC
    3. Convert each model to dictionary with serialized values
    
    Response Structure:
    - Array of file objects containing:
      - uuid: String representation of file's unique identifier
      - name: Original filename as uploaded
      - folder_path: Virtual folder path where file is stored
      - size: File size in bytes
      - created_at: ISO-8601 formatted creation timestamp
    
    Empty State:
    - Returns empty array ([]) if user has no files
    - Still returns 200 OK status code, not 404
    
    Performance Considerations:
    - No pagination implemented - may be slow for users with many files
    - Consider adding pagination parameters (limit/offset or cursor)
    - No GCS calls - purely database operation
    
    Usage Context:
    - Called when displaying file listings in UI
    - Full refresh of file list should be infrequent
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
    Generate a time-limited signed URL to access a file in GCS.
    
    Implementation Details:
    - Does NOT serve file content directly through API
    - Returns a signed GCS URL valid for 5 minutes
    - User accesses file directly from GCS via redirect or client-side fetch
    - Preserves original filename in Content-Disposition header
    - Content-Type set based on file extension or defaults to octet-stream
    - Uses retry logic with exponential backoff for GCS URL generation
    
    Flow:
    1. Verify file exists and belongs to user
    2. Construct GCS blob path using consistent pattern
    3. Generate signed URL with appropriate headers
    4. Return URL to client (not the file content)
    
    GCS Integration:
    - Uses DiskManager.generate_signed_url_with_retry for resilience
    - URL includes content-disposition header for proper filename
    - Content-type determined from file extension
    
    URL Parameters:
    - preview: Boolean flag controlling content-disposition
      - True: inline (browser renders if possible)
      - False: attachment (forces download)
    
    Response Structure:
    - String containing the signed GCS URL
    
    Security Considerations:
    - URLs expire after 5 minutes
    - URL is scoped to specific file (can't access other files)
    - User authorization verified before URL generation
    
    Error States:
    - 404: File not found or doesn't belong to user
    - 500: GCS URL generation failure after retries
    
    Usage Context:
    - Called when user wants to download or preview a file
    - Client should handle redirecting to the URL or embedding it (for preview)
    """
    response = await service.get_file_response(file_uuid, current_user.uid, session, preview)
    if response is None:
        raise HTTPException(status_code=404, detail="File not found")
    return response

@storage_router.post("/upload_file", status_code=status.HTTP_201_CREATED)
async def upload_file(
    file_name: str = Form(...),
    folder_path: str = Form(""),
    file_size: int = Form(100 * 1024 * 1024),
    content_type: str = Form("application/octet-stream"),
    client_origin: str = Form(None),  # Add this parameter to accept the client origin
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Stage 1 of two-phase upload process: prepare metadata and generate signed upload URL.
    
    Implementation Details:
    - Now supports both direct and resumable uploads to handle CORS issues
    - Client can specify its origin to be included in the GCS request
    - Creates database record BEFORE actual file upload (confirmed=False)
    - Returns a signed URL with PUT permissions for direct client→GCS upload
    - URL expires after 5 minutes for security
    - Storage quota is verified before allowing upload
    - Virtual folder structure maintained via folder_path parameter
    
    Database Flow:
    1. Check if file with same name exists in same folder (409 if exists)
    2. Check if upload would exceed user's 400MB quota (413 if exceeded)
    3. Create FileModel with confirmation=False
    4. Commit to database to get UUID for the file
    
    GCS Integration:
    - Blob name format: "{user_id}/{sanitized_user_id}_{file_uuid}_{file_name}"
    - Sanitizes filenames to prevent path traversal and invalid characters
    - Content type auto-detected or defaults to "application/octet-stream"
    
    Response Structure:
    - file_id: UUID of the created file record
    - upload_url: Signed GCS URL for PUT operation
    - storage_usage: Object with usage metrics (MB and percentage)
    
    Security Considerations:
    - Signed URLs prevent unauthorized uploads
    - File size parameter helps prevent quota abuse
    - Requires confirmation step to prevent storage of failed uploads
    
    Required Follow-up:
    - Client must call /confirm_upload/{file_uuid} after successful upload
    - Unconfirmed uploads cleaned up after 24 hours by background task
    
    Error States:
    - 400: Missing filename
    - 409: File with same name exists in folder
    - 413: Upload would exceed storage quota
    - 500: Database error or GCS configuration issue
    """
    print("Client Origin:", client_origin)
    if not file_name:
        raise HTTPException(status_code=400, detail="Filename is required")

    # Get user's current storage usage
    current_usage = await service.get_user_storage_usage(current_user.uid, session)
    current_usage_mb = current_usage / (1024 * 1024)
    
    # Move all logic to the service
    upload_details = await service.upload_file(
        file_name=file_name,
        folder_path=folder_path,
        file_size=file_size,
        user_id=current_user.uid,
        session=session,
        content_type=content_type,
        client_origin=client_origin  # Pass through the client origin
    )

    # Calculate new storage usage
    new_usage = await service.get_user_storage_usage(current_user.uid, session)
    new_usage_mb = new_usage / (1024 * 1024)
    upload_details["storage_usage"] =  {
            "used_mb": round(new_usage_mb, 2),
            "total_mb": 400,
            "percentage": round((new_usage_mb / 400) * 100, 2)
        }

    print("Provided upload details:", upload_details)
    return upload_details


@storage_router.get("/confirm_upload/{file_uuid}", status_code=status.HTTP_200_OK)
async def confirm_upload(
    file_uuid: UUID,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """Stage 2 of two-phase upload process: confirm successful GCS upload."""
    # Get the file first to check if it's a placeholder
    file = await service.get_file(file_uuid, current_user.uid, session)
    
    if not file:
        raise HTTPException(status_code=404, detail="File not found")
        
    # If it's already a placeholder, it's already confirmed
    if file.name == ".folder_placeholder":
        # Get updated storage usage
        current_usage = await service.get_user_storage_usage(current_user.uid, session)
        current_usage_mb = current_usage / (1024 * 1024)
        
        return {
            "message": "Placeholder file already confirmed",
            "storage_usage": {
                "used_mb": round(current_usage_mb, 2),
                "total_mb": 400,
                "percentage": round((current_usage_mb / 400) * 100, 2)
            }
        }
    
    # Normal confirmation for regular files
    upload_status = await service.confirm_file_upload(file_uuid, current_user.uid, session)
    if not upload_status:
        raise HTTPException(status_code=404, detail="File not found")
    
    # Get updated storage usage
    current_usage = await service.get_user_storage_usage(current_user.uid, session)
    current_usage_mb = current_usage / (1024 * 1024)
    
    return {
        "message": "File confirmed successfully",
        "storage_usage": {
            "used_mb": round(current_usage_mb, 2),
            "total_mb": 400,
            "percentage": round((current_usage_mb / 400) * 100, 2)
        }
    }

@storage_router.delete("/delete_file/{file_uuid}", status_code=status.HTTP_200_OK)
async def delete_file(
    file_uuid: UUID, 
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_session)
):
    """
    Delete a specific file from both GCS storage and database.
    
    Implementation Details:
    - Transactional approach: delete from GCS first, then database
    - Preserves database integrity if GCS deletion fails
    - If GCS deletion fails, database record is preserved (logged error)
    - Uses retry logic with exponential backoff for GCS deletion
    
    Delete Flow:
    1. Verify file exists and belongs to user
    2. Generate GCS blob path
    3. Delete from GCS (with retries)
    4. If GCS delete succeeds, delete database record
    5. Return success with updated storage usage
    
    Transaction Management:
    - GCS delete attempted first to prevent orphaned blobs
    - Database transaction only committed if GCS delete succeeds
    - Rollback occurs if any step fails
    
    Response Structure:
    - message: Success confirmation
    - storage_usage: Updated storage metrics after deletion
    
    Error States:
    - 404: File not found or doesn't belong to user
    - 500: Database error (GCS errors logged but return 200 if DB succeeds)
    
    Usage Context:
    - Called when user deletes a single file
    - Updates storage usage immediately for UI
    """
    result = await service.delete_file(file_uuid, current_user.uid, session)
    
    if result is None:
        raise HTTPException(status_code=404, detail="File not found")
        
    # Get updated storage usage
    current_usage = await service.get_user_storage_usage(current_user.uid, session)
    current_usage_mb = current_usage / (1024 * 1024)
    
    if result:
        return {
            "message": "File deleted successfully",
            "storage_usage": {
                "used_mb": round(current_usage_mb, 2),
                "total_mb": 400,
                "percentage": round((current_usage_mb / 400) * 100, 2)
            }
        }
    else:
        # The service.delete_file method already logs the error
        return {
            "message": "File deletion initiated, but GCS deletion failed. File may still exist in storage.",
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
    Explore a virtual folder to list its files and immediate subfolders.
    
    Implementation Details:
    - Implements virtual folder structure (not actual GCS folders)
    - URL decodes the folder_path parameter to handle spaces and special chars
    - Special handling for root folder (empty path) to show top-level items
    - Only shows immediate subfolders, not their contents (single level)
    - For non-root folders, verifies folder exists before listing
    - Suggests similar folders if folder doesn't exist (typo correction)
    
    Virtual Folder System:
    - Folders are virtual constructs stored in file.folder_path
    - No physical folders in GCS - just a path prefix in blob names
    - Allows hierarchical organization without GCS folder limitations
    
    Database Queries:
    - Root folder: Select all files, extract unique top-level folders
    - Non-root: Select files in exact folder + immediate child folders
    - Uses SQL LIKE patterns for efficient folder matching
    
    Response Structure:
    - Mixed array of folder and file objects:
      - Folders: {"type": "folder", "name": "folder-name", "path": "full/path"}
      - Files: {"type": "file", "name": "filename", ... other file metadata}
    - Items sorted alphabetically by name (folders then files)
    - Empty array if folder exists but has no contents
    
    Error Handling:
    - If folder doesn't exist: 404 with suggestions for similar folders
    - URL decoding handles spaces and special characters in paths
    
    Edge Cases:
    - Trailing slashes in paths are normalized
    - Case-sensitive folder matching (consider adding case-insensitive option)
    
    Usage Context:
    - Called when browsing folders in UI
    - Enables tree-like navigation of virtual folder structure
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
    
    Implementation Details:
    - Recursive deletion of all files in folder and subfolders
    - URL decodes the folder_path parameter to handle spaces and special chars
    - Transactional approach with GCS-first deletion
    - Could use batch operations for multiple files (currently sequential)
    - Continues partial deletion if some files fail (best-effort approach)
    
    Delete Flow:
    1. Find all files in folder and subfolders (SQL LIKE pattern)
    2. For each file:
       a. Generate GCS blob path
       b. Delete from GCS (with retries)
       c. If GCS delete succeeds, mark for DB deletion
    3. Commit database transaction to remove all successful deletions
    4. Return count of deleted files
    
    Transaction Management:
    - Single database transaction for all deletions
    - Each file verified individually with GCS before DB removal
    - Partial success possible (some files deleted, others remain)
    
    Response Structure:
    - message: Success with count of deleted files
    - storage_usage: Updated storage metrics after deletion
    
    Error States:
    - 404: Folder not found or empty
    - 500: Database transaction error or critical failure
    
    Performance Considerations:
    - For large folders, could be slow (sequential GCS operations)
    - Future improvement: Use GCS batch operations
    - No limit on number of files deleted in one operation
    
    Usage Context:
    - Called when user deletes an entire folder
    - High-impact operation that could delete many files
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

@staticmethod
def check_gcs_connection(bucket_name: str) -> bool:
    """Verify connection to GCS bucket."""
    try:
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        # Just check if we can list a single blob
        next(bucket.list_blobs(max_results=1), None)
        return True
    except Exception as e:
        logging.error(f"GCS connection check failed: {str(e)}")
        raise

