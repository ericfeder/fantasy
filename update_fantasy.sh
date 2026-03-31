#!/bin/bash

# Change to the directory where this script is located
cd "$(dirname "$0")"

# Run the Python update script
python update_fantasy.py

# Keep terminal open if run by double-clicking (only for macOS)
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo -e "\nPress any key to exit..."
    read -n 1
fi 