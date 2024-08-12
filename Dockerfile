# Use a base Python image that supports multiple platforms
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Copy application code and necessary files
COPY . .

# Install system dependencies including libffi-dev
RUN apt-get update \
    && apt-get install -y \
       build-essential \
       libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Upgrade pip and install Python dependencies
RUN pip install --upgrade pip \
    && pip install build twine \
    && pip install -r requirements.txt

# Build the package
RUN python -m build

# Command to run the application
CMD ["python", "ominis.py"]

# Optionally: define environment variables
ENV APP_ENV=production
ENV APP_DEBUG=False
