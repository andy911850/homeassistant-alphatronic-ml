# Alphatronics ML / UNii (Custom Component)

This is a specialized Home Assistant integration designed for **Alphatronics ML** and **UNii** alarm systems. 
It communicates via the local network (Port 6502) using a reverse-engineered binary protocol, specifically optimized for the **ML Series** panels.

**Current Version: v1.6.0**

## Key Features

*   **⚡ Optimistic UI**: Instant feedback for Arm/Disarm operations, providing a snappy user experience.
*   **🔒 Robust Security**:
    *   **Secure Bypass**: Bypass switches now use the standard 16-digit/8-byte protocol for perfect compatibility.
    *   **User Code Integration**: Safely retrieves your stored alarm code from Home Assistant configuration (supporting both initial setup and reconfiguration).
*   **📊 Accurate Monitoring**:
    *   **Smart State Detection**: Correctly identifies Open/Closed states using bit-level status analysis (Alarm, Tamper, Masking, Trouble).
    *   **Auto-Filtering**: Automatically hides empty or unused "VRIJE TEKST" zones to keep your dashboard clean.
*   **🔌 Stability First**:
    *   **Connection Management**: Uses a "Disconnect/Reconnect" strategy per poll to ensure fresh data and prevent stale connections.
    *   **Conflict Prevention**: Shared operation locks prevent command collisions during polling.

## Panel Configuration

To allow this integration to communicate with your alarm panel, you must configure the **General Interface** settings using the **AlphaTool** software.

1.  Open **AlphaTool** and connect to your panel.
2.  Navigate to **General Interface** settings.
3.  Configure the following settings:
    *   **Interface**: `Basic encryption`
    *   **Transport Protocol**: `TCP`
    *   **Port**: `6502`
    *   **Encryption key**: Enter an 8-character key (e.g., `12345678`). You will need this key during the Home Assistant setup.
    *   **Refresh rate**: `1s` (Required for fastest input response).

## Installation

1.  **HACS (Recommended)**:
    *   Go to **HACS > Integrations**.
    *   Click the three dots in the top right and select **Custom repositories**.
    *   Add `https://github.com/andy911850/homeassistant-alphatronic-ml` as a **Repository** with category **Integration**.
    *   Click **Install** on the **Alphatronics UNii (Custom)** integration.
2.  **Manual**:
    *   Copy the `custom_components/unii` folder to your Home Assistant's `config/custom_components/` directory.
3.  **Restart**: Restart Home Assistant.
4.  **Setup**:
    *   Go to **Settings > Devices & Services**.
    *   Click **Add Integration** and search for **UNii**.
    *   Enter your **Panel IP**, **Port** (6502), and **Shared Key**.

## Troubleshooting

### Connection Failed
If you see a "Connection failed" error:
1.  **Close AlphaTool**: The panel only supports **one** connection.
2.  **Hard Reboot Panel**: Disconnect AC and Battery for 15 seconds if the interface is frozen.

### Bypass Switch Issues
If you cannot toggle bypass switches:
1.  Ensure you have entered a **User Code** in the integration configuration.
2.  Update to **v1.6.0+** which allows fallback to default code '1234' and supports standard protocol formats.

## Acknowledgments & License

This project is an evolution of the original library and integration developed by [unii-security](https://github.com/unii-security).
Licensed under the **Apache License 2.0**.
