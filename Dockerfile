# Stage 1: Build dependencies
FROM python:3.11-slim AS builder
WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Stage 2: Final runtime image
FROM python:3.11-slim
WORKDIR /app

# Install runtime system dependencies (curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN addgroup --system --gid 1001 botgroup && \
    adduser --system --uid 1001 --gid 1001 botuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application code
COPY . .

# Set ownership to non-root user
RUN chown -R botuser:botgroup /app /opt/venv

# Switch to non-root user
USER botuser

# Activate virtual environment
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="/opt/venv/bin:$PATH"
ENV PYTHONPATH=/app

# Healthcheck – uses PORT (default 8000)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Запуск через start.sh
CMD ["sh", "./start.sh"]
