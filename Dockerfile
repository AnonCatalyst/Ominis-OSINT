# Use a base Python image that supports multiple platforms
FROM python:3.9-slim AS base

# Install system dependencies
RUN apt-get update \
    && apt-get install -y \
       build-essential \
       libffi-dev \
       curl \
       rustc \
       cargo \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install build twine \
    && pip install -r requirements.txt --break-system-packages

# Copy the rest of the application code
COPY . .

# Build the package
RUN python -m build

# Clean up
RUN apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the entry point
ENTRYPOINT ["python", "-m", "build"]

# Expose any ports (if needed)
# EXPOSE 8000
