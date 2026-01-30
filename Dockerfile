# JobTracker API Dockerfile
# Multi-stage build for optimized image size

# Build stage
FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt


# Runtime stage
FROM python:3.11-slim as runtime

WORKDIR /app

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash appuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Copy application code
COPY --chown=appuser:appuser src/ ./src/
COPY --chown=appuser:appuser api/ ./api/
COPY --chown=appuser:appuser mcp_server/ ./mcp_server/
COPY --chown=appuser:appuser scripts/ ./scripts/
COPY --chown=appuser:appuser config/ ./config/
COPY --chown=appuser:appuser pyproject.toml .

# Create cache directory
RUN mkdir -p /app/cache && chown appuser:appuser /app/cache

# Switch to non-root user
USER appuser

# Environment variables
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1
ENV API_HOST=0.0.0.0
ENV API_PORT=8000

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/health')" || exit 1

# Default command - run API
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
