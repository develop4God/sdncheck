# SDNCheck API Dockerfile
# Multi-stage build for optimized production image

# Stage 1: Build dependencies
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY python/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.11-slim

WORKDIR /app/python

# Install runtime dependencies only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash appuser

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local


# Copy only the api module and other needed files to /app/python
COPY python/api/ ./api/
COPY python/config_manager.py ./config_manager.py
COPY python/config.yaml ./config.yaml
COPY python/create_test_db_schema.py ./create_test_db_schema.py
COPY python/downloader.py ./downloader.py
COPY python/enhanced_xml.txt ./enhanced_xml.txt
COPY python/functional_test_db.py ./functional_test_db.py
COPY python/load_initial_data.py ./load_initial_data.py
COPY python/logo_base64.txt ./logo_base64.txt
COPY python/report_generator.py ./report_generator.py
COPY python/requirements.txt ../requirements.txt
COPY python/screener.py ./screener.py
COPY python/security_logger.py ./security_logger.py
COPY python/test_db_connection.py ./test_db_connection.py
COPY python/UNfile_format.txt ./UNfile_format.txt
COPY python/xml_utils.py ./xml_utils.py
COPY python/alembic.ini ./alembic.ini
COPY python/alembic/ ./alembic/
COPY python/database/ ./database/
COPY scripts/ ../scripts/

# Set permissions
RUN chown -R appuser:appuser /app \
    && chmod +x scripts/*.sh

# Switch to non-root user
USER appuser

# Add local bin to PATH
ENV PATH=/home/appuser/.local/bin:$PATH

# Environment variables (override in docker-compose or kubernetes)


ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 API_HOST=0.0.0.0

# Use Railway's PORT variable
EXPOSE ${PORT}

# Health check uses PORT
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:${PORT}/api/v1/health || exit 1

# Default command - Run the FastAPI server with uvicorn using PORT
CMD ["sh", "-c", "python -m uvicorn api.server:app --host 0.0.0.0 --port $PORT"]
