# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Prevent Python from buffering stdout/stderr and writing pyc files
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create a non-root system user
RUN groupadd -r appuser && useradd -r -g appuser appuser

WORKDIR /app

# Upgrade pip and install requirements leveraging docker build cache
COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application source code
COPY . /app

# Switch to the non-root user
USER appuser

EXPOSE 8000

# Run uvicorn natively. We recommend binding to 0.0.0.0 in Docker.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

