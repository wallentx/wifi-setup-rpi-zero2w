#!/bin/bash
set -e

# Detect context
SERVICE_USER=$(whoami)
SERVICE_GROUP=$(id -gn)
SERVICE_WORKING_DIR=$(pwd)

# Check for uv/venv
if [ -d ".venv" ]; then
    SERVICE_PYTHON_PATH="$SERVICE_WORKING_DIR/.venv/bin/python"
elif [ -f "/usr/bin/python3" ]; then
    # Fallback to system python if venv missing (though not recommended with uv)
    echo "Warning: .venv not found, falling back to system python"
    SERVICE_PYTHON_PATH="/usr/bin/python3"
else
    echo "Error: Could not find python interpreter."
    exit 1
fi

SERVICE_APP_PATH="$SERVICE_WORKING_DIR/app.py"

echo "Generating systemd service configuration..."
echo "  User: $SERVICE_USER"
echo "  Path: $SERVICE_WORKING_DIR"

# Generate the service file
sed -e "s|\\\${SERVICE_USER}|$SERVICE_USER|g" \
    -e "s|\\\${SERVICE_GROUP}|$SERVICE_GROUP|g" \
    -e "s|\\\${SERVICE_WORKING_DIR}|$SERVICE_WORKING_DIR|g" \
    -e "s|\\\${SERVICE_PYTHON_PATH}|$SERVICE_PYTHON_PATH|g" \
    -e "s|\\\${SERVICE_APP_PATH}|$SERVICE_APP_PATH|g" \
    wifi-setup.service.template > wifi-setup.service

echo "----------------------------------------------------------------"
echo "Service file 'wifi-setup.service' has been generated."
echo ""
echo "To install and enable the service, run:"
echo "  sudo cp wifi-setup.service /etc/systemd/system/"
echo "  sudo systemctl daemon-reload"
echo "  sudo systemctl enable wifi-setup.service"
echo "  sudo systemctl start wifi-setup.service"
echo "----------------------------------------------------------------"
