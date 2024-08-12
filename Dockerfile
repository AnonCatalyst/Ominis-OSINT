# Use a base Python image that supports multiple platforms
FROM python:3.9-slim AS base

# Install system dependencies
RUN apt-get update \
    && apt-get install -y \
       build-essential \
       libffi-dev \
       curl \
    && rm -rf /var/lib/apt/lists/*

# Install Rust and Cargo
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && export PATH="/root/.cargo/bin:$PATH" \
    && rustup update \
    && rustup component add rustfmt

# Set the working directory
WORKDIR /app

# Copy the package files
COPY . .

# Install Python dependencies
RUN pip install --upgrade pip \
    && pip install build twine \
    && pip install -r requirements.txt

# Build the package
RUN python -m build

# Set the entry point
ENTRYPOINT ["python", "-m", "build"]

# Expose any ports (if needed)
# EXPOSE 8000
