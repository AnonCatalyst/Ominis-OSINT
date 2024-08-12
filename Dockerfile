# Base image
FROM python:3.9-slim as base

# Install system dependencies
RUN apt-get update \
    && apt-get install -y \
       build-essential \
       libffi-dev \
       libssl-dev \
       libxml2-dev \
       libxslt-dev \
       zlib1g-dev \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Set up environment
WORKDIR /app

# Copy requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip==23.1.2 \
    && pip install --no-cache-dir -r requirements.txt --break-system-packages

# Copy application code
COPY . .

# Define entry point
ENTRYPOINT ["python"]
CMD ["ominis.py"]
