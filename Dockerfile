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
       curl \
    && rm -rf /var/lib/apt/lists/*

# Set up environment
WORKDIR /app

# Copy and install dependencies
COPY requirements.txt .
RUN pip install --upgrade pip==23.1.2 \
    && pip install --no-cache-dir -r requirements.txt --break-system-packages

# Copy application code
COPY . .

# Define entry point
ENTRYPOINT ["python"]
CMD ["ominis.py"]
