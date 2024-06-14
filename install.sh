#!/bin/bash
destination_dir="/usr/local/bin"

cp -r ../Ominis-OSINT "$destination_dir"

if [ $? -eq 0 ]; then
    echo "Copied Ominis-Osint folder to $destination_dir"
else
    echo "Failed to copy Ominis-Osint folder"
    exit 1
fi

# Making sure u dont get permission error when running the tool
chmod -R a+rw "$destination_dir/Ominis-Osint/src"

cd "$destination_dir/Ominis-Osint" || { echo "Failed to change directory"; exit 1; }

python3 -m venv venv

source venv/bin/activate

pip3 install -r requirements.txt

deactivate
chmod +x ominis
rm install.sh

# Making Sure The ominis runs when typing the command in
# Check if the user is using Bash
if [ -n "$BASH_VERSION" ]; then
    echo 'export PATH="$PATH:'"$destination_dir/Ominis-Osint"'"' >> ~/.bashrc
    echo "Added Ominis-Osint directory to PATH in ~/.bashrc"
fi

# Check if the user is using Zsh
if [ -n "$ZSH_VERSION" ]; then
    echo 'export PATH="$PATH:'"$destination_dir/Ominis-Osint"'"' >> ~/.zshrc
    echo "Added Ominis-Osint directory to PATH in ~/.zshrc"
fi

echo "Installation complete. You can now run ominis from anywhere in the terminal"
