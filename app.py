import subprocess
import time
from flask import Flask, render_template, request

app = Flask(__name__)

AP_NAME = "pirate"
AP_PASSWORD = "raspberry"

def is_connected():
    wifi_connected = subprocess.run(['iwgetid'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    eth_connected = subprocess.run(['ip', 'link', 'show', 'eth0'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return wifi_connected.returncode == 0 or eth_connected.returncode == 0

def start_ap():
    subprocess.run(["nmcli", "con", "add", "con-name", "hotspot", "ifname", "wlan0", "type", "wifi", "ssid", AP_NAME])
    subprocess.run(["nmcli", "con", "modify", "hotspot", "wifi-sec.key-mgmt", "wpa-psk"])
    subprocess.run(["nmcli", "con", "modify", "hotspot", "wifi-sec.psk", AP_PASSWORD])
    subprocess.run(["nmcli", "con", "modify", "hotspot", "802-11-wireless.mode", "ap", "802-11-wireless.band", "bg", "ipv4.method shared"])

def stop_ap():
    subprocess.run(["nmcli", "con", "down", "hotspot"], stderr=subprocess.DEVNULL)
    subprocess.run(["nmcli", "con", "delete", "hotspot"], stderr=subprocess.DEVNULL)

def get_available_networks():
    result = subprocess.run(["nmcli", "-t", "-f", "SSID", "dev", "wifi"], stdout=subprocess.PIPE)
    networks = result.stdout.decode().split("\n")
    return [net for net in networks if net]

def connect_to_network(ssid, password):
    stop_ap()
    subprocess.run(["nmcli", "dev", "wifi", "connect", ssid, "password", password])

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        ssid = request.form["network"]
        password = request.form["password"]
        connect_to_network(ssid, password)
        time.sleep(10)
        return render_template("status.html", status="Trying to connect...")

    networks = get_available_networks()
    return render_template("index.html", networks=networks)

if __name__ == "__main__":
    if not is_connected():
        start_ap()
    app.run(host="0.0.0.0", port=80)
