import os,datetime,logging,time,mimetypes
from google.cloud import storage
from storage.GCSClient import GCSClient

STORAGE_DIR = os.getenv("STORAGE_DIR", "storage")

class DiskManager:
        
    @staticmethod
    def generate_signed_url(bucket_name, blob_name, expiration_minutes=5):
        storage_client = GCSClient.get_client()  # Use singleton
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=expiration_minutes),
            method="GET",
            response_disposition=f'attachment; filename="{os.path.basename(blob_name)}"',
            response_type=mimetypes.guess_type(blob_name)[0] or "application/octet-stream",
        )

        return url

    @staticmethod
    def generate_signed_upload_url(bucket_name:str, blob_name:str, expiration:int=5, content_type:str=None):
        if content_type is None:
            # Guess based on filename
            content_type = mimetypes.guess_type(blob_name)[0] or "application/octet-stream"
        
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        url = blob.generate_signed_url(
            version="v4",
            expiration=datetime.timedelta(minutes=expiration),
            method="PUT",
            content_type=content_type
        )

        return url
    
    @staticmethod
    def delete_blob(bucket_name:str, blob_name:str, max_retries=3):
        """Delete a blob with retry logic."""
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)

        for attempt in range(max_retries):
            try:
                blob.delete()
                return True
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)  # Exponential backoff
                else:
                    logging.error(f"Failed to delete blob {blob_name} after {max_retries} attempts: {e}")
                    return False
    
    @staticmethod
    def delete_blobs_batch(bucket_name: str, blob_names: list) -> dict:
        """Delete multiple blobs in a single batch request."""
        from google.cloud.storage.batch import BatchClient
        
        storage_client = GCSClient.get_client()
        batch_client = BatchClient(storage_client)
        bucket = storage_client.bucket(bucket_name)
        
        results = {"successful": [], "failed": []}
        
        with batch_client:
            for blob_name in blob_names:
                try:
                    bucket.blob(blob_name).delete()
                    results["successful"].append(blob_name)
                except Exception as e:
                    logging.error(f"Failed to delete blob {blob_name}: {str(e)}")
                    results["failed"].append(blob_name)
        
        return results
    
    @staticmethod
    def blob_exists(bucket_name: str, blob_name: str) -> bool:
        """Check if a blob exists in the bucket."""
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        return blob.exists()
    
    @staticmethod
    def check_gcs_connection(bucket_name: str) -> bool:
        """Verify connection to GCS bucket."""
        try:
            storage_client = GCSClient.get_client()
            bucket = storage_client.bucket(bucket_name)
            # Just check if we can list a single blob
            next(bucket.list_blobs(max_results=1), None)
            return True
        except Exception as e:
            logging.error(f"GCS connection check failed: {str(e)}")
            raise
    
    @staticmethod
    def generate_signed_url_with_retry(bucket_name, blob_name, expiration_minutes=5, max_retries=3):
        """Generate signed URL with retry logic."""
        from tenacity import retry, stop_after_attempt, wait_exponential
        
        @retry(stop=stop_after_attempt(max_retries), wait=wait_exponential(multiplier=1, min=1, max=10))
        def _generate_url():
            return DiskManager.generate_signed_url(bucket_name, blob_name, expiration_minutes)
        
        try:
            return _generate_url()
        except Exception as e:
            logging.error(f"Failed to generate signed URL after {max_retries} attempts: {e}")
            raise


