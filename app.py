import logging
import subprocess
import time
import os
from flask import Flask, render_template, request, jsonify
from threading import Thread, Lock, Event

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

AP_NAME = os.environ.get("AP_NAME", "piratos")
AP_PASSWORD = os.environ.get("AP_PASSWORD", "raspberry")
try:
    CONNECTION_WAIT_TIME = int(os.environ.get("CONNECTION_WAIT_TIME", "10"))
except ValueError:
    logger.warning(
        "Invalid CONNECTION_WAIT_TIME value %r; using default 10",
        os.environ.get("CONNECTION_WAIT_TIME"),
    )
    CONNECTION_WAIT_TIME = 10

# Timing constants (configurable via environment variables / .env)
# AP_DURATION: total time (in seconds) to keep the access point active before shutting it down.
#              Default is 900 seconds (15 minutes) if AP_DURATION is not set in the environment.
try:
    AP_DURATION = int(os.environ.get("AP_DURATION", "900"))
except ValueError:
    logger.warning(
        "Invalid AP_DURATION value %r; using default 900",
        os.environ.get("AP_DURATION"),
    )
    AP_DURATION = 900
# RECONNECT_WINDOW: time window (in seconds) to keep trying to connect to the target WiFi network
#                   after credentials are submitted. Default is 120 seconds (2 minutes).
try:
    RECONNECT_WINDOW = int(os.environ.get("RECONNECT_WINDOW", "120"))
except ValueError:
    logger.warning(
        "Invalid RECONNECT_WINDOW value %r; using default 120",
        os.environ.get("RECONNECT_WINDOW"),
    )
    RECONNECT_WINDOW = 120

# Store connection attempt state
connection_state = {
    "in_progress": False,
    "ssid": None,
    "timestamp": None,
    "success": None,
    "error": None,
    "manual_failure": False,  # Flag to indicate recent manual connection failure
}
connection_state_lock = Lock()
connection_attempt_lock = Lock()  # Prevent concurrent connection attempts

# Global event to signal the manager thread to wake up/check state
manager_wake_event = Event()
manager_stop_event = Event()


def is_connected():
    wifi_connected = subprocess.run(
        ["iwgetid"], stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    eth0_info = subprocess.run(
        ["ip", "addr", "show", "eth0"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    eth_connected = False
    if eth0_info.returncode == 0:
        output = eth0_info.stdout
        # Check if interface is UP and has an inet (IPv4) address
        if "state UP" in output and "inet " in output:
            eth_connected = True
    return wifi_connected.returncode == 0 or eth_connected


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
        # First ensure no residual AP exists
        stop_ap()

        out = subprocess.run(
            [
                "nmcli",
                "con",
                "add",
                "con-name",
                "hotspot",
                "ifname",
                "wlan0",
                "type",
                "wifi",
                "ssid",
                AP_NAME,
            ],
            capture_output=True,
            text=True,
        )
        log_subprocess_output(out)
        if out.returncode != 0:
            raise RuntimeError(
                f"Failed to add hotspot: {out.stderr.strip() or out.stdout.strip()}"
            )

        out = subprocess.run(
            ["nmcli", "con", "modify", "hotspot", "wifi-sec.key-mgmt", "wpa-psk"],
            capture_output=True,
            text=True,
        )
        log_subprocess_output(out)
        if out.returncode != 0:
            raise RuntimeError(
                f"Failed to set key management: {out.stderr.strip() or out.stdout.strip()}"
            )

        out = subprocess.run(
            ["nmcli", "con", "modify", "hotspot", "wifi-sec.psk", AP_PASSWORD],
            capture_output=True,
            text=True,
        )
        log_subprocess_output(out)
        if out.returncode != 0:
            raise RuntimeError(
                f"Failed to set hotspot password: {out.stderr.strip() or out.stdout.strip()}"
            )

        out = subprocess.run(
            [
                "nmcli",
                "con",
                "modify",
                "hotspot",
                "802-11-wireless.mode",
                "ap",
                "802-11-wireless.band",
                "bg",
                "ipv4.method",
                "shared",
            ],
            capture_output=True,
            text=True,
        )
        log_subprocess_output(out)
        if out.returncode != 0:
            raise RuntimeError(
                f"Failed to set hotspot mode and band: {out.stderr.strip() or out.stdout.strip()}"
            )

        # Bring up the configured hotspot connection so the AP actually starts broadcasting
        out = subprocess.run(
            ["nmcli", "con", "up", "hotspot", "ifname", "wlan0"],
            capture_output=True,
            text=True,
        )
        log_subprocess_output(out)
        if out.returncode != 0:
            raise RuntimeError(
                f"Failed to bring up hotspot: {out.stderr.strip() or out.stdout.strip()}"
            )

        logger.info(f"AP '{AP_NAME}' started successfully")
    except Exception as e:
        logger.error(f"Failed to start AP: {e}")
        # Try to clean up partially created connection
        stop_ap()
        raise


def stop_ap():
    """Stop the access point if it exists."""
    result = subprocess.run(
        ["nmcli", "-t", "-f", "NAME", "con", "show"], stdout=subprocess.PIPE, text=True
    )

    connection_names = [line.strip() for line in result.stdout.splitlines()]
    if "hotspot" in connection_names:
        logger.info("Stopping existing AP")
        subprocess.run(["nmcli", "con", "down", "hotspot"], stderr=subprocess.DEVNULL)
        subprocess.run(["nmcli", "con", "delete", "hotspot"], stderr=subprocess.DEVNULL)
    else:
        logger.debug("No AP to stop")


def get_available_networks():
    result = subprocess.run(
        ["nmcli", "-t", "-f", "SSID", "dev", "wifi"], stdout=subprocess.PIPE
    )
    networks = result.stdout.decode().split("\n")
    return [net for net in networks if net]


def validate_network_input(ssid, password):
    """Validate SSID and password inputs to prevent command injection and ensure valid format."""
    # SSID validation (802.11 standard: max 32 bytes)
    if not ssid:
        raise ValueError("SSID is required")
    # Check byte length for Unicode support
    if len(ssid.encode("utf-8")) > 32:
        raise ValueError("SSID must be 32 bytes or fewer")

    # Password validation for WPA/WPA2/WPA3-Personal: 8-63 ASCII characters
    # Note: This follows the standard PSK (Pre-Shared Key) requirements
    if not password:
        raise ValueError("Password is required")

    # Ensure password contains only ASCII characters (required for WPA PSK)
    try:
        password.encode("ascii")
    except UnicodeEncodeError:
        raise ValueError("Password must contain only ASCII characters")

    # Validate length (ASCII characters are 1 byte each, so character count = byte count)
    if len(password) < 8 or len(password) > 63:
        raise ValueError("Password must be between 8 and 63 characters")

    # Check for null bytes which could be used for injection
    if "\0" in ssid or "\0" in password:
        raise ValueError("SSID and password cannot contain null bytes")

    return True


def connect_to_network(ssid, password):
    """Connect to a WiFi network. Input validation should be done by caller.

    Note: Password is passed as command line argument which may be visible in process lists.
    This is a known limitation of using nmcli in this manner. For production use, consider
    using nmcli's connection profile approach or stdin input for better security.
    """
    stop_ap()
    result = subprocess.run(
        ["nmcli", "dev", "wifi", "connect", ssid, "password", password],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return result.returncode == 0, result.stdout.decode(), result.stderr.decode()


def connection_manager():
    """
    Background thread that manages the connection state machine.
    Cycle:
    1. Check connection.
    2. If connected -> Wait and monitor.
    3. If disconnected ->
       a. Ensure AP is down (allow NM to auto-connect).
       b. Wait RECONNECT_WINDOW (e.g. 2 mins) for connection.
       c. If still disconnected -> Start AP.
       d. Wait AP_DURATION (e.g. 15 mins).
       e. Stop AP.
       f. Loop back to 1.
    """
    logger.info("Connection manager started")

    while not manager_stop_event.is_set():
        try:
            # 1. Check if user is actively trying to connect via UI
            with connection_state_lock:
                in_progress = connection_state["in_progress"]

            if in_progress:
                # User is attempting connection, don't interfere.
                time.sleep(2)
                continue

            # 2. Check current connection status
            if is_connected():
                logger.debug("Device is connected. Monitoring...")
                # Sleep for 60s, but wakeable if user starts an action
                manager_wake_event.wait(timeout=60)
                manager_wake_event.clear()
                continue

            # 3. Disconnected: Attempt Reconnect Phase
            logger.info("Device disconnected. Entering reconnection phase.")
            stop_ap()

            # Check if this is due to a recent manual connection failure
            # If so, skip the reconnect window and go straight to AP mode
            with connection_state_lock:
                skip_reconnect = connection_state["manual_failure"]
                if skip_reconnect:
                    connection_state["manual_failure"] = False
                    logger.info(
                        "Manual connection failed. Skipping reconnect window, starting AP immediately."
                    )

            if not skip_reconnect:
                # Trigger a rescan to help NetworkManager find networks
                subprocess.run(
                    ["nmcli", "dev", "wifi", "rescan"], stderr=subprocess.DEVNULL
                )

                # Wait for reconnection (RECONNECT_WINDOW)
                # Check frequently to see if we connected or if user took action
                start_wait = time.time()
                connected_during_wait = False

                while time.time() - start_wait < RECONNECT_WINDOW:
                    if manager_stop_event.is_set():
                        return

                    with connection_state_lock:
                        if connection_state["in_progress"]:
                            # User took action, break out of wait loop to top
                            break

                    if is_connected():
                        logger.info("Reconnected successfully during wait window!")
                        connected_during_wait = True
                        break

                    time.sleep(5)

                if connected_during_wait:
                    continue

                # If we broke because of user action, loop back to top
                with connection_state_lock:
                    if connection_state["in_progress"]:
                        continue

            # 4. Reconnection Failed: AP Phase
            logger.info(f"Reconnection failed. Starting AP for {AP_DURATION} seconds.")
            try:
                start_ap()
            except Exception:
                logger.exception("Failed to start AP. Will retry cycle.")
                time.sleep(30)
                continue

            # Wait for AP_DURATION
            # Check frequently for user action or magical connection (e.g. ethernet)
            start_ap_time = time.time()
            while time.time() - start_ap_time < AP_DURATION:
                if manager_stop_event.is_set():
                    stop_ap()
                    return

                with connection_state_lock:
                    if connection_state["in_progress"]:
                        # User submitted WiFi credentials via UI. The connect_to_network function will stop the AP.
                        # We exit this AP wait loop so the manager can proceed with the WiFi connection attempt.
                        logger.info("User initiated connection. Exiting AP wait loop.")
                        break

                # If ethernet is plugged in, we might be connected even with AP up
                # (though unlikely to route correctly without bridge, but `is_connected` checks eth0)
                if is_connected():
                    logger.info("Connection detected (possibly Ethernet). Stopping AP.")
                    stop_ap()
                    break

                time.sleep(5)

            # 5. End of AP Phase
            # Loop will restart, which checks connection (likely false),
            # then calls stop_ap() (redundant but safe), then enters Reconnect Window.
            logger.info("AP Phase ended. Cycling back to reconnection phase.")
        except Exception:
            logger.exception(
                "Unexpected error in connection_manager loop. Will retry after 30s."
            )
            time.sleep(30)


def manual_connect_task(ssid, password):
    """Task run by the web request thread to connect."""

    # Signal manager to wake up and see 'in_progress'
    manager_wake_event.set()

    # Prevent concurrent connection attempts
    if not connection_attempt_lock.acquire(blocking=False):
        logger.warning("Connection attempt already in progress, ignoring new request")
        # Update state so the UI can show an appropriate error for this request
        with connection_state_lock:
            connection_state["in_progress"] = False
            connection_state["success"] = False
            connection_state["error"] = (
                "Another connection attempt is already in progress"
            )
            connection_state["timestamp"] = time.time()
        return

    try:
        # Update state
        with connection_state_lock:
            connection_state["in_progress"] = True
            connection_state["ssid"] = ssid
            connection_state["timestamp"] = time.time()
            connection_state["success"] = None
            connection_state["error"] = None

        # Attempt connection
        # Note: connect_to_network handles stop_ap()
        success, stdout, stderr = connect_to_network(ssid, password)
        last_error = stderr.strip() if not success else None

        if success:
            # Wait for connection to stabilize
            time.sleep(CONNECTION_WAIT_TIME)

            # Verify connection
            if is_connected():
                logger.info(f"Successfully connected to {ssid}")
            else:
                success = False
                last_error = "Connection established but verification failed"
        else:
            logger.warning(f"Connection attempt failed: {last_error}")

        # Update state based on final result
        with connection_state_lock:
            connection_state["in_progress"] = False
            connection_state["success"] = success
            connection_state["error"] = last_error
            # Set manual_failure flag so connection_manager skips reconnect window
            connection_state["manual_failure"] = not success

        if not success:
            logger.info(
                "Manual connection failed. Connection manager will restart AP immediately."
            )

    finally:
        connection_attempt_lock.release()
        manager_wake_event.set()  # Wake manager to update status immediately


@app.route("/check_status")
def check_status():
    """Endpoint to check current connection status."""
    with connection_state_lock:
        conn_state = connection_state.copy()

    connected = is_connected()

    return jsonify(
        {
            "connected": connected,
            "in_progress": conn_state["in_progress"],
            "ssid": conn_state["ssid"],
            "success": conn_state["success"],
            "error": sanitize_output(conn_state["error"])
            if conn_state["error"]
            else None,
        }
    )


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        ssid = request.form["network"]
        password = request.form["password"]

        # Validate input before proceeding
        try:
            validate_network_input(ssid, password)
        except ValueError as e:
            return render_template(
                "status.html", status=f"Invalid input: {str(e)}", checking=False
            )

        # Start background connection thread
        thread = Thread(target=manual_connect_task, args=(ssid, password))
        thread.start()

        # Return immediately with a status page that will poll for updates
        return render_template("status.html", status="Connecting...", checking=True)

    networks = get_available_networks()
    return render_template("index.html", networks=networks)


if __name__ == "__main__":
    manager_thread = None
    try:
        # Start the manager thread
        manager_thread = Thread(target=connection_manager, daemon=False)
        manager_thread.start()

        app.run(host="0.0.0.0", port=8080)
    except Exception:
        # Log any unexpected exceptions during startup or runtime
        logger.exception("Unhandled exception in main application loop")
        raise
    finally:
        # Cleanup on shutdown
        logger.info("Shutting down...")
        manager_stop_event.set()
        manager_wake_event.set()
        # if manager_thread is not None:
        #     manager_thread.join()  # Optional: wait for it to stop
