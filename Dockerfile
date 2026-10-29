FROM python:3.11-slim

WORKDIR /app

# Install system dependencies:
# - curl for HTTP/2 upstream requests
# - wget for healthcheck
# - xvfb & chromium for self-sufficient 24/7 Turnstile resolution directly on VPS
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    xvfb \
    chromium \
    chromium-driver \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies (including playwright)
COPY requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Copy all application files
COPY . /app

# Configure environment:
# DISPLAY=:99 allows Chromium to run with a real virtual desktop under Xvfb
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0 \
    DISPLAY=:99 \
    REFRESH_INTERVAL=300

# Expose container port
EXPOSE 8000

# Container healthcheck for Coolify / Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8000/health || exit 1

# Start Xvfb virtual display in background, then launch server.py
CMD ["sh", "-c", "Xvfb :99 -screen 0 1280x1024x24 -ac & exec python server.py"]
