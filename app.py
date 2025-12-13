import logging
import subprocess
import time
import os
from flask import Flask, render_template, request, jsonify
from threading import Thread, Lock

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

AP_NAME = os.environ.get("AP_NAME", "piratos")
AP_PASSWORD = os.environ.get("AP_PASSWORD", "raspberry")
CONNECTION_WAIT_TIME = int(os.environ.get("CONNECTION_WAIT_TIME", "10"))  # Seconds to wait for connection to establish

# Store connection attempt state
connection_state = {
    'in_progress': False,
    'ssid': None,
    'timestamp': None,
    'success': None,
    'error': None
}
connection_state_lock = Lock()

def is_connected():
    wifi_connected = subprocess.run(['iwgetid'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    eth_connected = subprocess.run(['ip', 'link', 'show', 'eth0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return wifi_connected.returncode == 0 or eth_connected.returncode == 0


def log_subprocess_output(result):
    """Log subprocess output, treating stdout as info and stderr as error only on failure."""
    stdout_stripped = result.stdout.strip() if result.stdout else ""
    stderr_stripped = result.stderr.strip() if result.stderr else ""
    
    if stdout_stripped:
        logger.info(stdout_stripped)
    if stderr_stripped:
        if result.returncode != 0:
            logger.error(stderr_stripped)
        else:
            logger.info(stderr_stripped)


def start_ap():
    out = subprocess.run(
        ["nmcli", "con", "add", "con-name", "hotspot", "ifname", "wlan0", "type", "wifi", "ssid", AP_NAME], 
        capture_output=True, text=True
    )
    log_subprocess_output(out)
    if out.returncode != 0:
        raise RuntimeError(f"Failed to add hotspot: {out.stderr.strip() or out.stdout.strip()}")

    out = subprocess.run(
        ["nmcli", "con", "modify", "hotspot", "wifi-sec.key-mgmt", "wpa-psk"], 
        capture_output=True, text=True
    )
    log_subprocess_output(out)
    if out.returncode != 0:
        raise RuntimeError(f"Failed to set key management: {out.stderr.strip() or out.stdout.strip()}")

    out = subprocess.run(
        ["nmcli", "con", "modify", "hotspot", "wifi-sec.psk", AP_PASSWORD], 
        capture_output=True, text=True
    )
    log_subprocess_output(out)
    if out.returncode != 0:
        raise RuntimeError(f"Failed to set hotspot password: {out.stderr.strip() or out.stdout.strip()}")

    out = subprocess.run(
        ["nmcli", "con", "modify", "hotspot", "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg", "ipv4.method", "shared"], 
        capture_output=True, text=True
    )
    log_subprocess_output(out)
    if out.returncode != 0:
        raise RuntimeError(f"Failed to set hotspot mode and band: {out.stderr.strip() or out.stdout.strip()}")


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

def validate_network_input(ssid, password):
    """Validate SSID and password inputs to prevent command injection and ensure valid format."""
    # SSID validation (802.11 standard: max 32 bytes)
    if not ssid:
        raise ValueError("SSID is required")
    # Check byte length for Unicode support
    if len(ssid.encode('utf-8')) > 32:
        raise ValueError("SSID must be at most 32 bytes when encoded in UTF-8")
    
    # Password validation for WPA/WPA2/WPA3-Personal: 8-63 ASCII characters
    # Note: This follows the standard PSK (Pre-Shared Key) requirements
    if not password:
        raise ValueError("Password is required")
    
    # Ensure password contains only ASCII characters (required for WPA PSK)
    try:
        password.encode('ascii')
    except UnicodeEncodeError:
        raise ValueError("Password must contain only ASCII characters")
    
    # Validate length (ASCII characters are 1 byte each, so character count = byte count)
    if len(password) < 8 or len(password) > 63:
        raise ValueError("Password must be between 8 and 63 characters")
    
    # Check for null bytes which could be used for injection
    if '\0' in ssid or '\0' in password:
        raise ValueError("SSID and password cannot contain null bytes")
    
    return True

def connect_to_network(ssid, password):
    """Connect to a WiFi network. Input validation should be done by caller.
    
    Note: Password is passed as command line argument which may be visible in process lists.
    This is a known limitation of using nmcli in this manner. For production use, consider
    using nmcli's connection profile approach or stdin input for better security.
    """
    check_and_remove_hotspot()
    stop_ap()
    result = subprocess.run(["nmcli", "dev", "wifi", "connect", ssid, "password", password], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return result.returncode == 0, result.stdout.decode(), result.stderr.decode()

def background_connect(ssid, password):
    """Handle connection in background thread. Assumes input has already been validated."""
    global connection_state
    
    with connection_state_lock:
        connection_state['in_progress'] = True
        connection_state['ssid'] = ssid
        connection_state['timestamp'] = time.time()
        connection_state['success'] = None
        connection_state['error'] = None
    
    # Attempt to connect
    success, stdout, stderr = connect_to_network(ssid, password)
    
    # Wait a moment for connection to establish
    time.sleep(CONNECTION_WAIT_TIME)
    
    # Update state with result
    with connection_state_lock:
        connection_state['in_progress'] = False
        connection_state['success'] = success
        connection_state['error'] = stderr.strip() if not success else None

@app.route("/check_status")
def check_status():
    """Endpoint to check current connection status."""
    with connection_state_lock:
        connected = is_connected()
        return jsonify({
            'connected': connected,
            'in_progress': connection_state['in_progress'],
            'ssid': connection_state['ssid'],
            'success': connection_state['success'],
            'error': connection_state['error']
        })

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        ssid = request.form["network"]
        password = request.form["password"]
        
        # Validate input before proceeding
        try:
            validate_network_input(ssid, password)
        except ValueError as e:
            return render_template("status.html", status=f"Invalid input: {str(e)}", checking=False)
        
        # Start background connection thread
        thread = Thread(target=background_connect, args=(ssid, password))
        # Do not set thread.daemon = True; let the thread run to completion
        thread.start()
        
        # Return immediately with a status page that will poll for updates
        return render_template("status.html", status="Connecting...", checking=True)

    networks = get_available_networks()
    return render_template("index.html", networks=networks)

if __name__ == "__main__":
    if not is_connected():
        start_ap()
    app.run(host="0.0.0.0", port=80)
