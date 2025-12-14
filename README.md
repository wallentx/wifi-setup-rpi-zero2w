# WiFi Setup Portal for Raspberry Pi

This is a simple web-based interface that allows you to connect your Raspberry Pi to a Wi-Fi network. It checks if the Pi is connected to a network (via Wi-Fi or Ethernet) and if not, shows a portal to select a Wi-Fi network and enter the password.

## Prerequisites

Make sure you have the following installed on your Raspberry Pi:

- Python 3
- `pip3` (Python package manager)
- `nmcli` (NetworkManager)

## Installation

1. Install required dependencies:

```bash
sudo apt update
sudo apt install python3-pip python3-dev wireless-tools network-manager
```

2. Install Python libraries:

`sudo pip3 install flask`

3. Configure environment variables (optional):

The application uses environment variables for the access point name, password, and connection settings. You can customize these by copying the example file:

```bash
cp .env.example .env
nano .env
```

Edit the `.env` file to set your desired values.
*   `AP_NAME`: Hotspot SSID (default: "piratos")
*   `AP_PASSWORD`: Hotspot password (default: "raspberry")
*   `CONNECTION_WAIT_TIME`: Time in seconds to wait for connection verification (default: 10)

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

## API Endpoints

*   `GET /`: Main portal interface (lists networks).
*   `POST /`: Submits network credentials.
*   `GET /check_status`: JSON endpoint returning current connection status, used by the frontend for polling.

## Notes
*   The portal checks for both Wi-Fi and Ethernet (`eth0`) connections. If either is active, it reports as "Connected".