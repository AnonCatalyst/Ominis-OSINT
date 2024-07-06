#!/bin/bash

# Set the destination directory
destination_dir="/usr/local/bin"

# Check if cp alias is set, and unalias it if necessary
if [ "$(alias cp 2>/dev/null)" ]; then
  unalias cp
fi

# Copy the Ominis-OSINT folder
/usr/bin/cp -r ../Ominis-OSINT "$destination_dir"

# Check if the copy was successful
if [ $? -eq 0 ]; then
  echo "Copied Ominis-OSINT folder to $destination_dir"
else
  echo "Failed to copy Ominis-OSINT folder"
  exit 1
fi

# Set permissions for the src directory
chmod -R a+rw "$destination_dir/Ominis-OSINT/src"

# Change to the Ominis-OSINT directory
cd "$destination_dir/Ominis-OSINT" || { echo "Failed to change directory"; exit 1; }

# Create a virtual environment
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate

# Install dependencies
pip3 install -r requirements.txt

# Deactivate the virtual environment
deactivate

# Set execute permission on the ominis file
chmod +x ominis

# Remove the install script
rm install.sh

# Add the Ominis-OSINT directory to the system's PATH
if [ -n "$BASH_VERSION" ]; then
  # Bash shell
  echo 'export PATH="$PATH:'"$destination_dir/Ominis-OSINT"'"' >> ~/.bashrc
  echo "Added Ominis-OSINT directory to PATH in ~/.bashrc"
elif [ -n "$ZSH_VERSION" ]; then
  # Zsh shell
  echo 'export PATH="$PATH:'"$destination_dir/Ominis-OSINT"'"' >> ~/.zshrc
  echo "Added Ominis-OSINT directory to PATH in ~/.zshrc"
elif [ -n "$FISH_VERSION" ]; then
  # Fish shell
  echo 'set -gx PATH $PATH '"$destination_dir/Ominis-OSINT" >> ~/.config/fish/config.fish
  echo "Added Ominis-OSINT directory to PATH in ~/.config/fish/config.fish"
else
  # Other shells (e.g., Dash, Ksh)
  read -p "Your shell is not supported. Would you like to add the Ominis-OSINT directory to your system's PATH automatically? (y/n) " -n 1 -r
  echo
  if [[ $REPLY =~ ^[Yy]$ ]]; then
    # Add the directory to the PATH
    echo "export PATH=\"$PATH:$destination_dir/Ominis-OSINT\"" >> ~/.profile
    echo "Added Ominis-OSINT directory to PATH in ~/.profile"
    echo "Please restart your terminal or run 'source ~/.profile' to apply the changes."
  else
    echo "Ominis-OSINT will not be added to your system's PATH. You can still run it by navigating to the installation directory."
  fi
fi

echo "Installation complete. You can now run ominis from anywhere in the terminal"
