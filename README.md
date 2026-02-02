# Command Runner - Secure Mac Control for Home Assistant

Control your Mac remotely from Home Assistant with API key authentication.

## 🔒 Security First

This integration requires API key authentication. The server will reject all requests until you:
1. Generate at least one API key in Command Runner Settings
2. Provide that key when setting up the integration

## Installation

### Via HACS (Recommended)

1. Open HACS → Integrations
2. Click ⋮ → Custom repositories
3. Add: `https://github.com/yourusername/command_runner`
4. Category: Integration
5. Find "Command Runner" and click Download
6. Restart Home Assistant

### Manual

1. Copy `custom_components/command_runner` to your HA `custom_components` directory
2. Restart Home Assistant

## Setup

### 1. Generate API Key on Mac

1. Open Command Runner on your Mac
2. Go to Settings (⌘,)
3. Click "Generate Key..."
4. Name: "Home Assistant"
5. **Copy the generated key** (you won't see it again!)

### 2. Add Integration in Home Assistant

1. Settings → Devices & Services → Add Integration
2. Search: "Command Runner"
3. Enter:
   - **IP Address**: Your Mac's IP (e.g., 192.168.1.100)
   - **Port**: 8080 (or your custom port)
   - **API Key**: Paste the key you copied
4. Submit

## Error Messages

| Error | Solution |
|-------|----------|
| "Server has no API keys configured" | Generate a key in Command Runner Settings on your Mac |
| "Invalid API key" | Check you copied the entire key correctly |
| "Cannot connect" | Verify IP address, port, and that Command Runner is running |

## Usage

Each enabled command appears as a button entity that you can use in automations and dashboards.

## Troubleshooting

**403 Forbidden Error:**
- The Mac server has no API keys configured
- Solution: Open Command Runner → Settings → Generate Key

**401 Unauthorized Error:**
- Invalid or missing API key
- Solution: Verify the API key in Integration settings

**Connection Failed:**
- Check Mac IP address
- Verify port number
- Ensure Command Runner is running
- Check firewall settings

## License

MIT
