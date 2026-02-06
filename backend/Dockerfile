# Backend Dockerfile - Flask Python Application
# SECURITY: Runs as non-root user
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for Docker layer caching)
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create logs directory and non-root user
RUN mkdir -p logs && \
    useradd -m -u 1000 appuser && \
    chown -R appuser:appuser /app

# SECURITY: Switch to non-root user
USER appuser

# Expose Flask port
EXPOSE 5001

# Set environment variables
ENV FLASK_APP=app.py
ENV FLASK_ENV=production
ENV HOST=0.0.0.0
ENV PORT=5001

# Run the application
CMD ["python", "app.py"]
