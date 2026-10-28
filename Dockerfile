FROM python:3.11-alpine

WORKDIR /app

# Install curl for HTTP/2 support and wget for healthcheck
RUN apk add --no-cache curl

# Ensure unbuffered logs and clean bytecode
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8000 \
    HOST=0.0.0.0

# Copy application files
COPY . /app

# Expose container port
EXPOSE 8000

# Container healthcheck for Coolify / Docker
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8000/health || exit 1

# Start server
CMD ["python", "server.py"]
