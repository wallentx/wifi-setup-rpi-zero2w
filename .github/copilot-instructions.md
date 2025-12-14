# GitHub Copilot Instructions for WiFi Setup Portal

## Project Overview

This is a Flask-based web application designed for Raspberry Pi Zero 2W that provides a simple web interface for configuring WiFi networks. The application creates an access point when the Pi is not connected to a network, allowing users to connect and configure WiFi credentials through a web portal.

## Tech Stack

- **Backend**: Python 3, Flask
- **Frontend**: HTML (Jinja2 templates), CSS
- **Network Management**: NetworkManager (nmcli command-line tool)
- **Deployment**: systemd service on Raspberry Pi OS
- **Environment**: Raspberry Pi Zero 2W

## Coding Standards

### Python Code Style

- Follow PEP 8 style guidelines for Python code
- Use 4 spaces for indentation (not tabs)
- Maximum line length: 100 characters (flexible for readability)
- Use descriptive variable and function names
- Add docstrings for functions that have complex behavior or non-obvious side effects
- Keep functions focused and single-purpose

### Security Best Practices

**CRITICAL**: This application handles sensitive network credentials. Always prioritize security:

1. **Input Validation**: Always validate and sanitize user inputs
   - Use the existing `validate_network_input()` function as a template
   - Check for command injection risks (null bytes, shell metacharacters)
   - Validate SSID length (max 32 bytes UTF-8)
   - Validate password requirements (8-63 ASCII characters for WPA)

2. **Logging**: Never log passwords or sensitive credentials
   - Use the existing `sanitize_output()` function to redact passwords from logs
   - Apply sanitization to all subprocess output before logging

3. **Password Handling**:
   - Passwords are currently passed as command-line arguments (visible in process lists)
   - This is a known limitation when using nmcli
   - Document any security considerations in code comments

4. **Environment Variables**: Use `.env` file for configuration, never commit secrets
   - AP_NAME, AP_PASSWORD, CONNECTION_WAIT_TIME should be configurable

### HTML/CSS Guidelines

- Use semantic HTML5 elements
- Maintain accessibility standards (labels for inputs, proper form structure)
- Keep styling consistent with the existing dark theme
- Use the existing CSS color scheme:
  - Background: `#121212`
  - Text: `#e0e0e0` / `#ffffff`
  - Primary accent: `#1e88e5`
  - Input backgrounds: `#333`

### Flask Patterns

- Use Flask's `render_template()` for all HTML responses
- Use `jsonify()` for JSON API responses
- Follow the existing route structure (`/` for main page, `/check_status` for AJAX)
- Use threading for long-running operations (network connections)
- Always use thread-safe locks when updating shared state

## Project Structure

```
.
├── app.py                    # Main Flask application
├── templates/
│   ├── index.html           # Network selection form
│   └── status.html          # Connection status page
├── static/
│   └── style.css            # Application styles
├── .env.example             # Environment variable template
├── wifi_manager.service     # systemd service configuration
└── README.md                # Documentation
```

## Dependencies

### System Requirements
- Python 3
- NetworkManager (nmcli)
- wireless-tools

### Python Packages
- Flask (install with: `sudo pip3 install flask`)

**Note**: There is no `requirements.txt` file. Dependencies are documented in README.md.

## Setup and Build Instructions

### Development Setup
```bash
# Install system dependencies
sudo apt update
sudo apt install python3-pip python3-dev wireless-tools

# Install Python dependencies
sudo pip3 install flask

# Copy environment template (optional)
cp .env.example .env
# Edit .env to set custom AP_NAME and AP_PASSWORD
```

### Running the Application

**Development mode (port 8080, no root required)**:
```bash
python3 app.py
```

**Production mode (port 80, requires root)**:
```bash
sudo python3 app.py
```

### Testing
- **Manual testing**: Run the application and test with a web browser
- Currently no automated test suite exists
- When adding tests, consider:
  - Unit tests for validation functions
  - Integration tests for network operations (may require mocking)
  - Security tests for input validation

### Systemd Service Deployment
```bash
# Copy files to /opt/wifi_manager/
# Copy wifi_manager.service to /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable wifi_manager.service
sudo systemctl start wifi_manager.service
```

## Important Implementation Details

### Application Behavior
1. On startup, checks if device is connected to a network (WiFi or Ethernet)
2. If not connected, creates a WiFi access point (hotspot)
3. Users connect to the hotspot and access the web interface
4. After successful WiFi configuration, the hotspot is removed

### Threading Model
- Connection attempts run in background threads to avoid blocking the web server
- `connection_state` dict tracks connection progress
- Use `connection_state_lock` for thread-safe access
- Threads should NOT be set as daemon threads (let them complete)

### NetworkManager Integration
- All WiFi operations use `nmcli` command-line tool
- Always check return codes from subprocess calls
- Use `capture_output=True, text=True` for subprocess.run()
- Suppress stderr with `stderr=subprocess.DEVNULL` for cleanup operations

### Error Handling
- Return user-friendly error messages in web responses
- Log detailed technical errors for debugging
- Validate inputs before calling system commands

## Common Tasks

### Adding New Routes
```python
@app.route("/your-route", methods=["GET", "POST"])
def your_handler():
    # Your logic here
    return render_template("template.html", data=data)
```

### Adding Configuration Options
1. Add to `.env.example` with documentation
2. Load in `app.py` using `os.environ.get("VAR_NAME", "default")`
3. Document in README.md

### Modifying Network Operations
- Always validate inputs first
- Use existing helper functions (`validate_network_input`, `sanitize_output`)
- Test on actual Raspberry Pi hardware when possible
- Log operations for debugging

## Known Issues and Limitations

1. Passwords are visible in process lists when using nmcli (security consideration)
2. No automated tests currently exist
3. No requirements.txt file (dependencies documented in README)
4. Application requires root privileges to run on port 80 and manage network

## Best Practices for Contributions

1. **Minimal changes**: Make the smallest possible changes to achieve the goal
2. **Test on target hardware**: This is designed for Raspberry Pi - test there if possible
3. **Security first**: Always consider security implications of changes
4. **Preserve existing behavior**: Don't break working functionality
5. **Update documentation**: Keep README.md in sync with code changes
6. **Follow existing patterns**: Match the style and structure of existing code

## References

- Flask documentation: https://flask.palletsprojects.com/
- NetworkManager documentation: https://networkmanager.dev/
- Raspberry Pi OS documentation: https://www.raspberrypi.org/documentation/
