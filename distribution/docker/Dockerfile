FROM python:3.11-slim

LABEL maintainer="IntentOS Team"
LABEL description="IntentOS — AI execution layer where files never leave your device"

WORKDIR /app

# System deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

# Create non-root user
RUN useradd -m -s /bin/bash intentos
USER intentos

# Default workspace
RUN mkdir -p /home/intentos/.intentos/workspace/outputs

EXPOSE 7891 5173

ENTRYPOINT ["python", "core/kernel_v2.py"]
