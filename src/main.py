from src.StorageApp.routes import storage_router
from fastapi import FastAPI, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
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

app.include_router(storage_router, prefix="/storage", tags=["Storage"])