import logging
import subprocess
import time
from flask import Flask, render_template, request

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

AP_NAME = "piratos"
AP_PASSWORD = "raspberry"

def is_connected():
    wifi_connected = subprocess.run(['iwgetid'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    eth_connected = subprocess.run(['ip', 'link', 'show', 'eth0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return wifi_connected.returncode == 0 or eth_connected.returncode == 0


def log_subprocess_output(result):
    """Log subprocess output, treating stdout as info and stderr as error."""
    if result.stdout:
        logger.info(result.stdout.strip())
    if result.stderr:
        logger.error(result.stderr.strip())


def start_ap():
    out = subprocess.run(
        ["nmcli", "con", "add", "con-name", "hotspot", "ifname", "wlan0", "type", "wifi", "ssid", AP_NAME], 
        capture_output=True, text=True
    )
    log_subprocess_output(out)

    out = subprocess.run(
        ["nmcli", "con", "modify", "hotspot", "wifi-sec.key-mgmt", "wpa-psk"], 
        capture_output=True, text=True
    )
    log_subprocess_output(out)

    out = subprocess.run(
        ["nmcli", "con", "modify", "hotspot", "wifi-sec.psk", AP_PASSWORD], 
        capture_output=True, text=True
    )
    log_subprocess_output(out)

    out = subprocess.run(
        ["nmcli", "con", "modify", "hotspot", "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg", "ipv4.method", "shared"], 
        capture_output=True, text=True
    )
    log_subprocess_output(out)


def stop_ap():
    subprocess.run(["nmcli", "con", "down", "hotspot"], stderr=subprocess.DEVNULL)
    subprocess.run(["nmcli", "con", "delete", "hotspot"], stderr=subprocess.DEVNULL)

def get_available_networks():
    result = subprocess.run(["nmcli", "-t", "-f", "SSID", "dev", "wifi"], stdout=subprocess.PIPE)
    networks = result.stdout.decode().split("\n")
    return [net for net in networks if net]

def check_and_remove_hotspot():
    """Check for existing hotspot connections and remove them if found."""
    result = subprocess.run(["nmcli", "con", "show"], stdout=subprocess.PIPE, text=True)
    connections = result.stdout.splitlines()
    
    for connection in connections:
        if "hotspot" in connection:
            subprocess.run(["nmcli", "con", "down", "hotspot"], stderr=subprocess.DEVNULL)
            subprocess.run(["nmcli", "con", "delete", "hotspot"], stderr=subprocess.DEVNULL)
            logger.info(f"Removed hotspot connection: {connection}")

def connect_to_network(ssid, password):
    check_and_remove_hotspot()
    stop_ap()
    result = subprocess.run(["nmcli", "dev", "wifi", "connect", ssid, "password", password], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0, result.stdout.decode(), result.stderr.decode()

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        ssid = request.form["network"]
        password = request.form["password"]
        success, stdout, stderr = connect_to_network(ssid, password)
        time.sleep(10)
        if is_connected():
            return render_template("status.html", status="Connected successfully!")
        else:
            error_message = stderr.strip() or "Failed to connect to the network."
            return render_template("status.html", status=f"Connection failed: {error_message}")

    networks = get_available_networks()
    return render_template("index.html", networks=networks)

if __name__ == "__main__":
    if not is_connected():
        start_ap()
    app.run(host="0.0.0.0", port=80)
