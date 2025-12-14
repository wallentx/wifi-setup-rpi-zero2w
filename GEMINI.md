# Project Context: WiFi Setup Portal for Raspberry Pi

## Project Overview
This project is a Flask-based web application designed to simplify the process of connecting a Raspberry Pi (specifically the Zero 2 W) to a WiFi network. It functions as a captive portal: if the Pi is not connected to a network (checked via `nmcli` for WiFi and `ip` for Ethernet), it creates its own Access Point (AP). Users can connect to this AP, navigate to a web interface, and configure the Pi's WiFi credentials.

## Architecture & Key Components
*   **Framework:** Python Flask.
*   **Network Management:** Relies on `nmcli` (NetworkManager) to scan for networks, manage the hotspot (`AP_NAME`/`AP_PASSWORD`), and connect to WiFi.
*   **Concurrency:** Uses Python `threading` to handle connection attempts in the background (`background_connect` function) without blocking the web server.
*   **API:**
    *   `GET /`: Serves the network selection UI (`index.html`).
    *   `POST /`: Accepts SSID/Password to initiate connection.
    *   `GET /check_status`: Returns JSON status (`connected`, `in_progress`, `success`, `error`) for frontend polling.
*   **Configuration:** Uses environment variables loaded from a `.env` file.

## Key Files
*   **`app.py`**: The core application logic. Handles the web server, network checks (`is_connected`), AP management (`start_ap`/`stop_ap`), and threaded connection logic.
*   **`wifi_manager.service`**: A systemd service file configured for a production-like deployment using a dedicated `wifi_manager` user in `/opt/wifi_manager/`.
*   **`.env.example`**: Template for configuration (`AP_NAME`, `AP_PASSWORD`, `CONNECTION_WAIT_TIME`).
*   **`templates/`**: Contains the HTML interfaces (`index.html` for the network list, `status.html` for connection progress/polling).

## Installation & Setup

### Prerequisites
*   Raspberry Pi (Zero 2 W recommended)
*   OS: Raspberry Pi OS (Linux)
*   System Tools: `nmcli` (NetworkManager), `wireless-tools`
*   Python 3 & `pip`

### Step-by-Step Setup
1.  **Install System Dependencies:**
    ```bash
    sudo apt update
    sudo apt install python3-pip python3-dev wireless-tools network-manager
    ```

2.  **Install Python Dependencies:**
    ```bash
    sudo pip3 install flask
    ```

3.  **Configuration:**
    Copy `.env.example` to `.env` and configure:
    *   `AP_NAME`: Hotspot SSID.
    *   `AP_PASSWORD`: Hotspot password.
    *   `CONNECTION_WAIT_TIME`: Wait time for connection verification.

## Running the Application

### Manual Execution
```bash
sudo python3 app.py
```
*   Runs on port **8080**.
*   Requires `sudo` for network operations.

### Service Deployment (Systemd)
The project provides `wifi_manager.service` for a specific deployment structure:
*   **Path:** `/opt/wifi_manager/`
*   **User:** `wifi_manager` (must be created)
*   **Capabilities:** Uses `CAP_NET_ADMIN` to allow network changes without full root.

*Alternative:* Users can manually create a service file to run as the `pi` user from the home directory (documented in `README.md`).

## Development Conventions
*   **Logging:** Logs to stdout/stderr. Passwords are redacted in logs using `sanitize_output`.
*   **Security:**
    *   `validate_network_input` prevents injection and validates SSID/password length/format.
    *   `connection_state_lock` ensures thread safety during connection attempts.
*   **Network Logic:** Checks `wlan0` for WiFi and `eth0` for wired connections.