from pydantic_settings import BaseSettings,SettingsConfigDict
from dotenv import load_dotenv
load_dotenv()

import os
print("🧐 CWD when loading .env:", os.getcwd())
print("🧐 Do we see a .env here?", os.path.exists(os.path.join(os.getcwd(), ".env")))

class Settings(BaseSettings):
    DATABASE_URL : str
    JWT_SECRET: str = "dev-secret-key"  # Default for development only
    JWT_ALGORITHM: str = "HS256"        # Default algorithm
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

