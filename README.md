# WiFi Setup Portal for Raspberry Pi

This is a simple web-based interface that allows you to connect your Raspberry Pi to a Wi-Fi network. It checks if the Pi is connected to a network and if not, shows a portal to select a Wi-Fi network and enter the password.

## Prerequisites

Make sure you have the following installed on your Raspberry Pi:

- Python 3
- `pip3` (Python package manager)

## Installation

1. Install required dependencies:

```bash
sudo apt update
sudo apt install python3-pip python3-dev wireless-tools
```

2. Install Python libraries:

`sudo pip3 install flask`

3. Configure environment variables (optional):

The application uses environment variables for the access point name and password. You can customize these by copying the example file:

```bash
cp .env.example .env
nano .env
```

Edit the `.env` file to set your desired AP_NAME and AP_PASSWORD. If not configured, the application will use default values (AP_NAME: "piratos", AP_PASSWORD: "raspberry").

## Running the Application

1. Clone or download the repository to your Raspberry Pi.

2. Navigate to the project folder and run the application:

`sudo python3 app.py`

The web portal will be available at http://your-pi-ip:80

## Setting up Autostart using systemd
To ensure the application starts automatically on boot using systemd, follow these steps:

1. Create a new systemd service file:
`sudo nano /etc/systemd/system/wifi-setup.service`

2. Add the following content to the file:

```
[Unit]
Description=WiFi Setup Portal
After=network.target

[Service]
ExecStart=/usr/bin/python3 /path/to/your/project/app.py
WorkingDirectory=/path/to/your/project
User=pi
Group=pi
Restart=always
# Load environment variables from .env file (optional)
EnvironmentFile=-/path/to/your/project/.env

[Install]
WantedBy=multi-user.target
```

Make sure to replace /path/to/your/project/ with the actual path to your project directory.

**Note:** If you want to use custom AP_NAME and AP_PASSWORD values, create a `.env` file in your project directory with the following content:
```
AP_NAME=your_custom_ap_name
AP_PASSWORD=your_custom_password
```

Alternatively, you can use the included `wifi_manager.service` file which is configured for installation in `/opt/wifi_manager/`. To use it:
- Copy your project files to `/opt/wifi_manager/`
- If using custom credentials, create `/opt/wifi_manager/.env` with your AP_NAME and AP_PASSWORD
- Copy `wifi_manager.service` to `/etc/systemd/system/`

3. Enable and start the service:
```
sudo systemctl daemon-reload
sudo systemctl enable wifi-setup.service
sudo systemctl start wifi-setup.service
```
4. Check the status of the service:
`sudo systemctl status wifi-setup.service`

Your application will now automatically start on boot and be available on port 80.

## Notes
The portal will be available on port 80, and you can access it via any device connected to the Raspberry Pi's network.
If the Pi is already connected to a network, it will display a "Connected" message.
