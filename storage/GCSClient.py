from google.cloud import storage


class GCSClient:
    _instance = None

    @classmethod
    def get_client(cls):
        if cls._instance is None:
            cls._instance = storage.Client()
        return cls._instance