from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv
load_dotenv()

import os
print("🧐 CWD when loading .env:", os.getcwd())
print("🧐 Do we see a .env here?", os.path.exists(os.path.join(os.getcwd(), ".env")))

class Settings(BaseSettings):
    JWT_SECRET : str
    JWT_ALGORITHM : str
    STORAGE_DIR : str
    DATABASE_URL  : str
    GOOGLE_CLIENT_SECRET : str
    GOOGLE_CLIENT_ID : str
    SMTP_USERNAME : str
    SMTP_PASSWORD : str
    EMAIL_FROM : str
    SMTP_PORT : int
    SMTP_SERVER : str

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30  # Default token expiration time in minutes
    # Application URL for email links
    APP_URL: str = "http://127.0.0.1:8000/auth"

    model_config  = SettingsConfigDict(
         env_file = ".env",
         extra = "ignore"
    )


Config = Settings()
print("🚀 Inside Config gile Config loaded, DB URL is: ", Config.DATABASE_URL)
import os
from dotenv import load_dotenv
load_dotenv()
db_url = os.getenv("DATABASE_URL")
# config.set_main_option("sqlalchemy.url", db_url)
print("🚀 Inside Config gile Config loaded, DB URL is 2: ", db_url)
print("🚀 Inside Config gile Config loaded, Storage Dir URL is 2: ", os.getenv("STORAGE_DIR"))

