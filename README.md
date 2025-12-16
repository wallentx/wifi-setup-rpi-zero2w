# WiFi Setup Portal for Raspberry Pi

This is a simple web-based interface that allows you to connect your Raspberry Pi to a Wi-Fi network. It checks if the Pi is connected to a network (via Wi-Fi or Ethernet) and if not, shows a portal to select a Wi-Fi network and enter the password.

## Features

- **Automatic AP Mode**: Creates a WiFi access point when no connection is available
- **Web-based Configuration**: Simple interface to select and connect to WiFi networks
- **Automatic Retry**: Retries connection attempts before falling back to AP mode
- **Connection Monitoring**: Continuously monitors connection health in the background
- **Automatic Fallback**: If connection drops, automatically restarts AP mode
- **Circuit Breaker Protection**: Prevents rapid restart loops with exponential backoff
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

### Basic Configuration
*   `AP_NAME`: Hotspot SSID (default: "piratos")
*   `AP_PASSWORD`: Hotspot password (default: "raspberry") - **IMPORTANT**: Change this before deployment!
*   `CONNECTION_WAIT_TIME`: Time in seconds to wait for connection verification (default: 10)

### Connection Monitoring & Retry
*   `MONITOR_INTERVAL`: Seconds between connection health checks (default: 30)
*   `CONNECTION_RETRIES`: Number of retry attempts before falling back to AP (default: 1)
*   `RETRY_DELAY`: Seconds to wait between retry attempts (default: 5)

### Circuit Breaker Configuration
*   `MAX_RESTARTS_PER_WINDOW`: Maximum AP restarts allowed within time window (default: 3)
*   `RESTART_WINDOW`: Time window for counting restarts in seconds (default: 300 = 5 minutes)
*   `BACKOFF_BASE`: Exponential backoff base (default: 6, creates sequence: 5s → 30s → 3min)

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

### Connection Monitoring
- A background thread checks connection health every 30 seconds (configurable)
- If connection drops: Automatically restarts AP mode
- If multiple rapid failures occur: Circuit breaker applies exponential backoff

### Circuit Breaker
- Prevents excessive restart loops that could drain battery or cause system instability
- Default: After 3 restarts in 5 minutes, applies exponential backoff delays: 30s → 180s (3min) → 1080s (18min) → capped at 1 hour
- **Warning:** The exponential backoff grows rapidly. After each failure beyond the restart threshold, the delay increases exponentially and is capped at 1 hour maximum to ensure the AP eventually restarts. Restart the service to reset the backoff.
- Resets immediately upon successful connection (restart history also expires after 5 minutes)

## API Endpoints

*   `GET /`: Main portal interface (lists networks).
*   `POST /`: Submits network credentials.
*   `GET /check_status`: JSON endpoint returning current connection status and monitoring state.
    - Returns: `connected`, `in_progress`, `ssid`, `success`, `error`, `state`, `ap_mode`, `monitoring`, `last_ssid`, `restart_backoff`

## Troubleshooting

### Connection Fails Immediately
- Check that the WiFi network is in range and accessible
- Verify the password is correct (8-63 ASCII characters required)
- Check logs: `sudo journalctl -u wifi_manager.service -f` (if using systemd)

### AP Doesn't Restart After Connection Failure
- This feature requires the updated code with automatic fallback
- Check that the application started successfully: `sudo systemctl status wifi_manager`
- Verify monitoring is active by checking logs for "Connection monitor started"

### Circuit Breaker Engaged (Long Delays)
- If you see "Applying circuit breaker backoff" in logs, the system detected repeated failures
- This is normal behavior to prevent restart loops
- Wait for the backoff period, or restart the service to reset: `sudo systemctl restart wifi_manager`
- Consider increasing `CONNECTION_WAIT_TIME` if your network is slow to establish connections

### Connection Monitor Not Working
- Ensure the application has permissions to run `iwgetid` and `ip` commands
- Check that NetworkManager is installed and running: `sudo systemctl status NetworkManager`
- Verify `MONITOR_INTERVAL` is set to a reasonable value (default: 30 seconds)

## Notes
*   The portal checks for both Wi-Fi and Ethernet (`eth0`) connections. If either is active, it reports as "Connected".