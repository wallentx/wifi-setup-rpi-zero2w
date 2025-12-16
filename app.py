import logging
import subprocess
import time
import os
from flask import Flask, render_template, request, jsonify
from threading import Thread, Lock, Event

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

AP_NAME = os.environ.get("AP_NAME", "piratos")
AP_PASSWORD = os.environ.get("AP_PASSWORD", "raspberry")
CONNECTION_WAIT_TIME = int(os.environ.get("CONNECTION_WAIT_TIME", "10"))  # Seconds to wait for connection to establish (configurable via env)

# Connection monitoring and retry configuration
MONITOR_INTERVAL = int(os.environ.get("MONITOR_INTERVAL", "30"))  # Seconds between connection health checks
CONNECTION_RETRIES = int(os.environ.get("CONNECTION_RETRIES", "1"))  # Number of retry attempts before falling back to AP
RETRY_DELAY = int(os.environ.get("RETRY_DELAY", "5"))  # Seconds to wait between retry attempts
MAX_RESTARTS_PER_WINDOW = int(os.environ.get("MAX_RESTARTS_PER_WINDOW", "3"))  # Circuit breaker: max restarts before backoff
RESTART_WINDOW = int(os.environ.get("RESTART_WINDOW", "300"))  # Circuit breaker: time window in seconds
BACKOFF_BASE = int(os.environ.get("BACKOFF_BASE", "6"))  # Circuit breaker: exponential backoff base
MAX_BACKOFF = int(os.environ.get("MAX_BACKOFF", "3600"))  # Circuit breaker: maximum backoff delay in seconds (default: 1 hour)

# Store connection attempt state
connection_state = {
    'in_progress': False,
    'ssid': None,
    'timestamp': None,
    'success': None,
    'error': None
}
connection_state_lock = Lock()
connection_attempt_lock = Lock()  # Prevent concurrent connection attempts

# Store connection monitoring state
connection_monitor_state = {
    'state': 'DISCONNECTED',  # CONNECTED, CONNECTING, FAILED, MONITORING, AP_MODE
    'monitor_active': False,
    'last_ssid': None,
    'restart_history': [],  # List of restart timestamps
    'current_backoff': 0,   # Current backoff delay in seconds
    'monitor_thread': None,
    'stop_event': Event()   # Event for immediate thread wake-up
}
monitor_state_lock = Lock()

def is_connected():
    wifi_connected = subprocess.run(['iwgetid'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    eth0_info = subprocess.run(['ip', 'addr', 'show', 'eth0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    eth_connected = False
    if eth0_info.returncode == 0:
        output = eth0_info.stdout
        # Check if interface is UP and has an inet (IPv4) address
        if "state UP" in output and "inet " in output:
            eth_connected = True
    return wifi_connected.returncode == 0 or eth_connected


def calculate_backoff(restart_history):
    """Calculate backoff delay based on restart history.

    Implements circuit breaker pattern to prevent rapid restart loops.
    Returns backoff delay in seconds.
    """
    current_time = time.time()
    cutoff_time = current_time - RESTART_WINDOW

    # Count restarts within the time window
    recent_restarts = [t for t in restart_history if t > cutoff_time]
    restart_count = len(recent_restarts)

    if restart_count >= MAX_RESTARTS_PER_WINDOW:
        # Apply exponential backoff with cap
        excess_restarts = restart_count - MAX_RESTARTS_PER_WINDOW + 1
        backoff = RETRY_DELAY * (BACKOFF_BASE ** excess_restarts)
        # Cap the backoff to prevent it from growing unbounded
        backoff = min(backoff, MAX_BACKOFF)
        logger.warning(f"Circuit breaker: {restart_count} restarts in {RESTART_WINDOW}s window. Applying {backoff}s backoff (capped at {MAX_BACKOFF}s).")
        return backoff

    return 0


def record_ap_restart():
    """Record AP restart timestamp and update backoff state."""
    global connection_monitor_state

    with monitor_state_lock:
        current_time = time.time()
        connection_monitor_state['restart_history'].append(current_time)

        # Clean up old entries
        cutoff_time = current_time - RESTART_WINDOW
        connection_monitor_state['restart_history'] = [
            t for t in connection_monitor_state['restart_history'] if t > cutoff_time
        ]

        # Calculate and update current backoff
        connection_monitor_state['current_backoff'] = calculate_backoff(
            connection_monitor_state['restart_history']
        )


def attempt_ap_restart():
    """Helper to perform the actual AP restart."""
    stop_ap()
    start_ap()


def safe_restart_ap():
    """Safely restart AP with circuit breaker protection."""
    global connection_monitor_state

    try:
        # Record the restart before calculating backoff
        record_ap_restart()

        # Check current backoff after recording
        with monitor_state_lock:
            backoff = connection_monitor_state['current_backoff']

        if backoff > 0:
            logger.info(f"Applying circuit breaker backoff: waiting {backoff}s before restarting AP")
            time.sleep(backoff)

        logger.info("Restarting Access Point...")
        attempt_ap_restart()

        # Update state
        with monitor_state_lock:
            connection_monitor_state['state'] = 'AP_MODE'

        logger.info("Access Point restarted successfully")

    except Exception as e:
        logger.error(f"Failed to restart AP: {str(e)}")
        with monitor_state_lock:
            connection_monitor_state['state'] = 'FAILED'

        # On AP start failure, wait longer before next attempt
        logger.warning("Will retry AP start after 60 seconds")
        time.sleep(60)

        # Try one more time
        try:
            attempt_ap_restart()
            # Don't record retry as a separate restart - it's part of the same attempt
            with monitor_state_lock:
                connection_monitor_state['state'] = 'AP_MODE'
            logger.info("Access Point restarted successfully on retry")
        except Exception as retry_error:
            logger.error(f"Failed to restart AP on retry: {str(retry_error)}")
            with monitor_state_lock:
                connection_monitor_state['state'] = 'FAILED'


def connection_monitor_loop():
    """Background monitoring loop that checks connection health periodically."""
    global connection_monitor_state

    logger.info("Connection monitor started")
    
    # Get reference to stop event (it's never reassigned)
    stop_event = connection_monitor_state['stop_event']

    while True:
        try:
            # Check if monitoring should stop (quick check with lock)
            with monitor_state_lock:
                if not connection_monitor_state['monitor_active']:
                    logger.info("Connection monitor stopping")
                    break
                current_state = connection_monitor_state['state']
            
            # Check connection status outside the lock
            connected = is_connected()

            # Atomically update state as needed
            restart_ap = False
            with monitor_state_lock:
                # Re-check state in case it changed
                current_state = connection_monitor_state['state']
                
                # If we were monitoring and connection dropped
                if current_state == 'MONITORING' and not connected:
                    logger.warning("Connection drop detected! Restarting AP...")
                    connection_monitor_state['state'] = 'DISCONNECTED'
                    restart_ap = True
                # If we're connected but not in monitoring state, transition to monitoring
                elif current_state == 'CONNECTED' and connected:
                    connection_monitor_state['state'] = 'MONITORING'
                    logger.info("Connection stable, entering monitoring mode")

            # Restart AP outside the lock to avoid deadlock
            if restart_ap:
                safe_restart_ap()

        except Exception as e:
            logger.error(f"Error in connection monitor loop: {str(e)}")
            # Continue monitoring despite errors
        
        # Wait for MONITOR_INTERVAL or until stop_event is set
        if stop_event.wait(timeout=MONITOR_INTERVAL):
            # Event was set, meaning we should stop
            logger.info("Connection monitor stopping (event triggered)")
            break


def start_connection_monitor():
    """Start the connection monitoring thread."""
    global connection_monitor_state

    with monitor_state_lock:
        # Don't start if already active
        if connection_monitor_state['monitor_active']:
            logger.debug("Connection monitor already active")
            return

        connection_monitor_state['monitor_active'] = True
        # Clear the stop event
        connection_monitor_state['stop_event'].clear()

        # Create and start non-daemon thread (let it complete)
        monitor_thread = Thread(target=connection_monitor_loop, daemon=False)
        monitor_thread.start()
        connection_monitor_state['monitor_thread'] = monitor_thread

    logger.info("Connection monitor thread started")


def stop_connection_monitor():
    """Stop the connection monitoring thread gracefully."""
    global connection_monitor_state

    with monitor_state_lock:
        if not connection_monitor_state['monitor_active']:
            logger.debug("Connection monitor not active")
            return

        connection_monitor_state['monitor_active'] = False
        # Set the stop event to wake up the thread immediately
        connection_monitor_state['stop_event'].set()
        monitor_thread = connection_monitor_state['monitor_thread']

    # Wait for thread to finish (with timeout)
    if monitor_thread and monitor_thread.is_alive():
        logger.info("Waiting for connection monitor to stop...")
        monitor_thread.join(timeout=5)

        if monitor_thread.is_alive():
            logger.warning("Connection monitor thread did not stop gracefully")
        else:
            logger.info("Connection monitor stopped")


def sanitize_output(output):
    """Redact sensitive information from subprocess output."""
    if not output:
        return output
    # Redact AP_PASSWORD if present
    return output.replace(AP_PASSWORD, "***REDACTED***")

def log_subprocess_output(result):
    """Log subprocess output, treating stdout as info and stderr as error only on failure."""
    stdout_stripped = result.stdout.strip() if result.stdout else ""
    stderr_stripped = result.stderr.strip() if result.stderr else ""

    sanitized_stdout = sanitize_output(stdout_stripped)
    sanitized_stderr = sanitize_output(stderr_stripped)
    
    if sanitized_stdout:
        logger.info(sanitized_stdout)
    if sanitized_stderr:
        if result.returncode != 0:
            logger.error(sanitized_stderr)
        else:
            logger.info(sanitized_stderr)


def start_ap():
    try:
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

        # Update state to indicate AP mode is active
        with monitor_state_lock:
            connection_monitor_state['state'] = 'AP_MODE'

        logger.info(f"AP '{AP_NAME}' started successfully")
    except Exception:
        # Update state to indicate failure
        with monitor_state_lock:
            connection_monitor_state['state'] = 'FAILED'
        raise


def stop_ap():
    """Stop the access point if it exists."""
    result = subprocess.run(
        ["nmcli", "con", "show"],
        stdout=subprocess.PIPE,
        text=True
    )

    if "hotspot" in result.stdout:
        logger.info("Stopping existing AP")
        subprocess.run(["nmcli", "con", "down", "hotspot"], stderr=subprocess.DEVNULL)
        subprocess.run(["nmcli", "con", "delete", "hotspot"], stderr=subprocess.DEVNULL)
    else:
        logger.debug("No AP to stop")

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
        raise ValueError("SSID must be 32 bytes or fewer")

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
    """Handle connection with retry and automatic AP fallback."""
    global connection_state, connection_monitor_state

    # Prevent concurrent connection attempts
    if not connection_attempt_lock.acquire(blocking=False):
        logger.warning("Connection attempt already in progress, ignoring new request")
        return

    try:
        # Update initial state
        with connection_state_lock:
            connection_state['in_progress'] = True
            connection_state['ssid'] = ssid
            connection_state['timestamp'] = time.time()
            connection_state['success'] = None
            connection_state['error'] = None

        with monitor_state_lock:
            connection_monitor_state['state'] = 'CONNECTING'
            connection_monitor_state['last_ssid'] = ssid

        # Stop connection monitor during connection attempt
        stop_connection_monitor()

        # Retry loop
        success = False
        last_error = None

        for attempt in range(CONNECTION_RETRIES + 1):
            if attempt > 0:
                logger.info(f"Retry attempt {attempt}/{CONNECTION_RETRIES} for {ssid}")
                time.sleep(RETRY_DELAY)

            # Attempt connection
            success, stdout, stderr = connect_to_network(ssid, password)
            last_error = stderr.strip() if not success else None

            if success:
                # Wait for connection to stabilize
                time.sleep(CONNECTION_WAIT_TIME)

                # Verify connection
                if is_connected():
                    logger.info(f"Successfully connected to {ssid}")
                    break
                else:
                    success = False
                    last_error = "Connection established but verification failed"
            else:
                logger.warning(f"Connection attempt failed: {last_error}")

        # Update state based on final result
        with connection_state_lock:
            connection_state['in_progress'] = False
            connection_state['success'] = success
            connection_state['error'] = last_error

        if success:
            # Start monitoring for connection drops
            with monitor_state_lock:
                connection_monitor_state['state'] = 'CONNECTED'
                # Reset backoff on successful connection
                connection_monitor_state['restart_history'].clear()
                connection_monitor_state['current_backoff'] = 0

            start_connection_monitor()
            logger.info("Connection monitor started")
        else:
            # Connection failed after all retries - restart AP
            logger.error(f"All connection attempts failed for {ssid}. Restarting AP mode.")
            with monitor_state_lock:
                connection_monitor_state['state'] = 'FAILED'

            # Restart AP after brief delay
            time.sleep(2)
            safe_restart_ap()
    finally:
        # Always release the lock
        connection_attempt_lock.release()

@app.route("/check_status")
def check_status():
    """Endpoint to check current connection status."""
    with connection_state_lock:
        conn_state = connection_state.copy()

    with monitor_state_lock:
        mon_state = connection_monitor_state.copy()

    connected = is_connected()

    return jsonify({
        'connected': connected,
        'in_progress': conn_state['in_progress'],
        'ssid': conn_state['ssid'],
        'success': conn_state['success'],
        'error': sanitize_output(conn_state['error']) if conn_state['error'] else None,
        'state': mon_state['state'],
        'ap_mode': mon_state['state'] == 'AP_MODE',
        'monitoring': mon_state['monitor_active'],
        'last_ssid': mon_state['last_ssid'],
        'restart_backoff': mon_state['current_backoff']
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
    try:
        if not is_connected():
            logger.info("No connection detected, starting AP mode")
            start_ap()
        else:
            logger.info("Connection detected, starting connection monitor")
            with monitor_state_lock:
                connection_monitor_state['state'] = 'CONNECTED'
            start_connection_monitor()

        app.run(host="0.0.0.0", port=8080)
    finally:
        # Cleanup on shutdown
        logger.info("Shutting down, stopping connection monitor")
        stop_connection_monitor()
