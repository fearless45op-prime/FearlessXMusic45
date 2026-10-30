FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH="/root/.deno/bin:${PATH}"

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    git \
    curl \
    ca-certificates \
    unzip \
    && rm -rf /var/lib/apt/lists/*

# Install Deno for YouTube JavaScript challenge solving
RUN curl -fsSL https://deno.land/install.sh | sh

# Verify Deno installation
RUN deno --version

WORKDIR /app

# Install Python dependencies
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir --upgrade "yt-dlp[default]"

# Create required directories
RUN mkdir -p /app/data /app/downloads /app/sessions

# Copy bot source
COPY . .

# Start bot
CMD ["python", "main.py"]
