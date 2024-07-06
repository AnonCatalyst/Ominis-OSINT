#!/bin/bash

# Set the installation directory
if [ "$(uname)" == "Darwin" ]; then
  # macOS
  destination_dir="/usr/local/bin"
else
  # Linux, Windows, etc.
  destination_dir="/usr/bin"
fi

# Create the installation directory if it doesn't exist
if [ ! -d "$destination_dir" ]; then
  sudo mkdir -p "$destination_dir"
fi

# Copy the current directory to the installation directory
sudo cp -r . "$destination_dir/Ominis-OSINT"

# Install requirements from requirements.txt
if [ "$(uname)" == "Darwin" ]; then
  # macOS (use pip3 to avoid conflicts with system Python)
  python3 -m pip install --break-system-packages -r requirements.txt
else
  # Linux, Windows, etc. (use pip to install packages)
  python -m pip install --break-system-packages -r requirements.txt
fi

# Add the Ominis-OSINT directory to the system's PATH
if [ "$(uname)" == "Darwin" ]; then
  # macOS (use bashrc for Bash and zshrc for Zsh)
  if [ -n "$BASH_VERSION" ]; then
    echo 'export PATH="$PATH:'"$destination_dir/Ominis-OSINT"'"' >> ~/.bashrc
    source ~/.bashrc
    echo "Added Ominis-OSINT directory to PATH in ~/.bashrc"
  elif [ -n "$ZSH_VERSION" ]; then
    echo 'export PATH="$PATH:'"$destination_dir/Ominis-OSINT"'"' >> ~/.zshrc
    source ~/.zshrc
    echo "Added Ominis-OSINT directory to PATH in ~/.zshrc"
  fi
elif [ "$(expr substr $(uname -s) 1 5)" == "Linux" ]; then
  # Linux (use bashrc for Bash and zshrc for Zsh)
  if [ -n "$BASH_VERSION" ]; then
    echo 'export PATH="$PATH:'"$destination_dir/Ominis-OSINT"'"' >> ~/.bashrc
    source ~/.bashrc
    echo "Added Ominis-OSINT directory to PATH in ~/.bashrc"
  elif [ -n "$ZSH_VERSION" ]; then
    echo 'export PATH="$PATH:'"$destination_dir/Ominis-OSINT"'"' >> ~/.zshrc
    source ~/.zshrc
    echo "Added Ominis-OSINT directory to PATH in ~/.zshrc"
  fi
elif [ "$(expr substr $(uname -s) 1 10)" == "MINGW64_NT" ]; then
  # Windows (use Git Bash or similar)
  echo 'export PATH="$PATH:'"$destination_dir/Ominis-OSINT"'"' >> ~/.bashrc
  source ~/.bashrc
  echo "Added Ominis-OSINT directory to PATH in ~/.bashrc"
elif [ "$(expr substr $(uname -s) 1 5)" == "Arch" ]; then
  # Arch Linux (use bashrc for Bash and zshrc for Zsh)
  if [ -n "$BASH_VERSION" ]; then
    echo 'export PATH="$PATH:'"$destination_dir/Ominis-OSINT"'"' >> ~/.bashrc
    source ~/.bashrc
    echo "Added Ominis-OSINT directory to PATH in ~/.bashrc"
  elif [ -n "$ZSH_VERSION" ]; then
    echo 'export PATH="$PATH:'"$destination_dir/Ominis-OSINT"'"' >> ~/.zshrc
    source ~/.zshrc
    echo "Added Ominis-OSINT directory to PATH in ~/.zshrc"
  fi
fi

echo "Installation complete."
