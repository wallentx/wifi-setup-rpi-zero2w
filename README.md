# WiFi Setup Portal for Raspberry Pi

This is a simple web-based interface that allows you to connect your Raspberry Pi to a Wi-Fi network. It checks if the Pi is connected to a network (via Wi-Fi or Ethernet) and if not, shows a portal to select a Wi-Fi network and enter the password.

## Features

- **Automatic AP Mode**: Creates a WiFi access point when no connection is available
- **Web-based Configuration**: Simple interface to select and connect to WiFi networks
- **Automatic Retry**: Retries connection attempts before falling back to AP mode
- **Connection Monitoring**: Continuously monitors connection health in the background
- **Automatic Fallback**: If connection drops, automatically restarts AP mode
- **Dual Network Support**: Respects both WiFi and Ethernet connections

## Prerequisites

Make sure you have the following installed on your Raspberry Pi:

- Python 3
- `uv` (Python package and project manager) - [Installation instructions](https://docs.astral.sh/uv/getting-started/installation/)
- `nmcli` (NetworkManager)

## Installation

1. Install required system dependencies:

```bash
sudo apt update
sudo apt install python3-dev wireless-tools network-manager
```

2. Install Python dependencies:

```bash
uv sync
```

3. Configure environment variables (optional):

The application uses environment variables for the access point name, password, and connection settings. You can customize these by copying the example file:

```bash
cp .env.example .env
nano .env
```

Edit the `.env` file to set your desired values.

### Configuration Options
*   `AP_NAME`: Hotspot SSID (default: "piratos")
*   `AP_PASSWORD`: Hotspot password (default: "raspberry") - **IMPORTANT**: Change this before deployment!
*   `CONNECTION_WAIT_TIME`: Time in seconds to wait for connection verification (default: 10)
*   `AP_DURATION`: Total time (in seconds) to keep the access point active before shutting it down (default: 900 = 15 minutes)
*   `RECONNECT_WINDOW`: Time window (in seconds) to keep trying to reconnect to the target WiFi network after connection is lost (default: 120 = 2 minutes)

## Running the Application

### Manual Execution

To run the application manually (useful for development):

```bash
# If using uv (recommended)
sudo uv run app.py

# Or using system python
sudo python3 app.py
```

*   Note: `sudo` is required for manual execution to give the script access to NetworkManager (`nmcli`) and network interfaces.

### Service Deployment (Recommended)

This project includes an installation script that automatically configures a systemd service to run as your current user (`$USER`) from the current directory.

1.  **Generate the service file:**
    ```bash
    ./install_service.sh
    ```
    This script will inspect your environment and create a `wifi-setup.service` file tailored to your user and path.

2.  **Install and Start:**
    Follow the instructions output by the script, which will look like this:
    ```bash
    sudo cp wifi-setup.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable wifi-setup.service
    sudo systemctl start wifi-setup.service
    ```

The service uses `AmbientCapabilities` (CAP_NET_ADMIN) to perform network operations without running the entire process as root.

## How It Works

### Initial Startup
- On startup, the application checks if the device is connected (WiFi or Ethernet)
- If not connected: Starts AP mode automatically
- If connected: Starts connection monitoring in the background

### Connection Flow
1. User connects to the AP and navigates to the web portal
2. User selects a WiFi network and enters credentials
3. AP shuts down and connection attempt begins
4. If connection succeeds: Monitoring starts, AP stays off
5. If connection fails: AP restarts immediately (no retry delay for manual attempts)

### Connection Monitoring and Automatic Fallback
The application includes a background connection manager that monitors the network connection and automatically falls back to AP mode if the connection is lost:

1. **Monitoring Phase**: Checks connection health every 60 seconds
2. **Reconnection Window**: If disconnected automatically (not due to manual connection failure), waits for 2 minutes (configurable via `RECONNECT_WINDOW`), checking for automatic reconnection every 5 seconds
3. **AP Fallback**: If reconnection fails, automatically starts the AP for 15 minutes (configurable via `AP_DURATION`)
4. **Cycle Repeats**: After AP duration expires, the manager attempts to reconnect again

**Note**: When a manual connection attempt fails (user-initiated via the UI), the AP is restarted immediately without the reconnection window wait to allow the user to retry quickly.

## API Endpoints

*   `GET /`: Main portal interface (lists networks).
*   `POST /`: Submits network credentials.
*   `GET /check_status`: JSON endpoint returning current connection status.
    - Returns: `connected`, `in_progress`, `ssid`, `success`, `error`

## Troubleshooting

### Connection Fails Immediately
- Check that the WiFi network is in range and accessible
- Verify the password is correct (8-63 ASCII characters required)
- Check logs: `sudo journalctl -u wifi_manager.service -f` (if using systemd)

### AP Doesn't Restart After Connection Failure
- Check that the application started successfully: `sudo systemctl status wifi_manager`
- Verify the connection manager thread is running by checking logs for "Connection manager started"
- The manager waits 2 minutes (RECONNECT_WINDOW) before restarting AP mode

### Connection Manager Not Working
- Ensure the application has permissions to run `iwgetid` and `ip` commands
- Check that NetworkManager is installed and running: `sudo systemctl status NetworkManager`

## Notes
*   The portal checks for both Wi-Fi and Ethernet (`eth0`) connections. If either is active, it reports as "Connected".