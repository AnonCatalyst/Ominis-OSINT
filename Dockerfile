# Use an official Python base image with support for multiple platforms
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y \
       build-essential \
       libffi-dev \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Install Rust and Cargo separately to handle potential issues
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && export PATH="/root/.cargo/bin:$PATH" \
    && rustup update \
    && rustup component add rustfmt

# Copy application code and necessary files
COPY . .

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
