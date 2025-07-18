from src.StorageApp.routes import storage_router
from src.Auth.routes import auth_router
from fastapi import FastAPI, status, BackgroundTasks
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import aiocron
import logging

# from contextlib import asynccontextmanager



app = FastAPI(title="YeRakh Storage Service", version="1.0.0")

# Middleware for CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for simplicity, adjust as needed
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods
    allow_headers=["*"],  # Allow all headers
)

@app.get("/health", status_code=status.HTTP_200_OK)
async def health_check():
    """
    Health check endpoint to verify if the service is running.
    """
    return JSONResponse(content={"status": "ok"}, status_code=status.HTTP_200_OK)   

# Setup scheduled tasks
@app.on_event("startup")
async def setup_scheduled_tasks():
    # Clean up unconfirmed uploads every day at 2 AM
    @aiocron.crontab("0 2 * * *")
    async def cleanup_unconfirmed_uploads():
        from src.StorageApp.services import StorageService
        service = StorageService()
        result = await service.cleanup_unconfirmed_uploads(max_age_hours=24)
        logging.info(f"Scheduled cleanup result: {result}")

app.include_router(storage_router, prefix="/storage", tags=["Storage"])
app.include_router(auth_router, prefix="/auth", tags=["Authentication"])