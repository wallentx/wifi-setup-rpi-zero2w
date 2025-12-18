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

1. Clone or download the repository to your Raspberry Pi.

2. Navigate to the project folder and run the application:

`sudo python3 app.py`

The web portal will be available at http://your-pi-ip:8080.
*   Note: `sudo` is required for NetworkManager access (creating hotspots, connecting to WiFi).

## Setting up Autostart using systemd

You have two options for setting up autostart: using the included service file (recommended) or creating one manually.

### Option 1: Using the included `wifi_manager.service`

This method assumes you will deploy the application to `/opt/wifi_manager/` and run it as a dedicated user `wifi_manager` for better security.

1.  Create the user and directory:
    ```bash
    sudo useradd -r -s /bin/false wifi_manager
    sudo mkdir /opt/wifi_manager
    sudo chown wifi_manager:wifi_manager /opt/wifi_manager
    ```
2.  Copy project files to `/opt/wifi_manager/`.
3.  Copy the service file:
    ```bash
    sudo cp wifi_manager.service /etc/systemd/system/
    ```
4.  Enable and start:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable wifi_manager.service
    sudo systemctl start wifi_manager.service
    ```

### Option 2: Manual Setup (Run as `pi`)

If you prefer to run it from your home directory as the `pi` user:

1. Create a new systemd service file:
`sudo nano /etc/systemd/system/wifi-setup.service`

2. Add the following content:

```ini
[Unit]
Description=WiFi Setup Portal
After=network.target

[Service]
ExecStart=/usr/bin/python3 /home/pi/path/to/your/project/app.py
WorkingDirectory=/home/pi/path/to/your/project
User=pi
Group=pi
Restart=always
# Load environment variables from .env file (optional)
EnvironmentFile=-/home/pi/path/to/your/project/.env

[Install]
WantedBy=multi-user.target
```

3. Enable and start:
```bash
sudo systemctl daemon-reload
sudo systemctl enable wifi-setup.service
sudo systemctl start wifi-setup.service
```

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
5. If connection fails: Retries once (configurable), then restarts AP

### Connection Monitoring and Automatic Fallback
The application includes a background connection manager that monitors the network connection and automatically falls back to AP mode if the connection is lost:

1. **Monitoring Phase**: Checks connection health every 60 seconds
2. **Reconnection Window**: If disconnected, waits for 2 minutes (configurable via `RECONNECT_WINDOW`), checking for automatic reconnection every 5 seconds
3. **AP Fallback**: If reconnection fails, automatically starts the AP for 15 minutes (configurable via `AP_DURATION`)
4. **Cycle Repeats**: After AP duration expires, the manager attempts to reconnect again

This ensures the device remains accessible for reconfiguration even if the WiFi network becomes unavailable.

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