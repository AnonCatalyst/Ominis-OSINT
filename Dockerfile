# Dockerfile for Arch Linux
FROM archlinux:latest

# Install Python and other dependencies
RUN pacman -Syu --noconfirm \
    && pacman -S --noconfirm python python-pip python-setuptools python-wheel \
    && pip install --upgrade pip \
    && pip install build twine

# Set working directory
WORKDIR /app

# Copy the package files
COPY . .

# Command to build the package
CMD ["python", "-m", "build"]
