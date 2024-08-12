⁷# Use a base Python image that supports multiple platforms
FROM python:3.9-slim

# Set the working directory
WORKDIR /app

# Install system dependencies including Rust and Cargo
RUN apt-get update \
    && apt-get install -y \
       build-essential \
       libffi-dev \
       curl \
    && rm -rf /var/lib/apt/lists/* \
    && curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y \
    && export PATH="$PATH:/root/.cargo/bin" \
    && rustup update

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
