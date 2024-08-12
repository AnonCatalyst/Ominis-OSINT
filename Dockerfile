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
FROM base AS rust

# Install Rust
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y

# Set the environment variable for Rust
ENV PATH="/root/.cargo/bin:${PATH}"

# Verify installation
RUN rustc --version \
    && cargo --version \
    && rustfmt --version

# Set the working directory
WORKDIR /app

# Copy the package files and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install build twine \
    && pip install -r requirements.txt

# Copy the rest of the application code
COPY . .

# Build the package
RUN python -m build

# Remove temporary files
RUN apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* /root/.cargo /root/.rustup

# Set the entry point
ENTRYPOINT ["python", "-m", "build"]

# Expose any ports (if needed)
# EXPOSE 8000
