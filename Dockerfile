FROM python:3.13-slim

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create a non-root user
RUN useradd -m appuser
USER appuser

# Run as a non-root user
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]