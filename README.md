# Alphatronics ML / UNii (Custom Component)

This is a specialized Home Assistant integration designed for **Alphatronics ML** and **UNii** alarm systems. 
It communicates via the local network (Port 6502) using a reverse-engineered binary protocol, specifically adapted to support the unique data format of the **ML Series** panels.

## Key Features

*   **ML Series Support**: Custom protocol handler for the **Alphatronics ML** legacy firmware (22-byte fixed-width zones, 2-byte status stride).
*   **Smart Filtering**: automatically hides empty "VRIJE TEKST" zones, keeping your dashboard clean.
*   **Robust Protocol**: Corrected implementation of the communication protocol (Input Arrangement), ensuring reliable connection even with complex panel configurations.
*   **Multi-Section Support**: Control individual alarm sections (e.g., Section 1, Section 2) independently.
*   **Master Control**: A composite Alarm Control Panel entity that monitors and controls the entire system.
*   **Intelligent Zone Monitoring**:
    *   **Automatic Naming**: Zones automatically use the names programmed on your panel (e.g., "Hallway PIR").
    *   **States**: Clear, Open, Bypassed.
    *   **Diagnostics**: Tamper detection, Anti-masking status, and Low Battery alerts.
*   **Bypass Switches**: 
    *   **Dedicated Platform**: Each security-relevant zone (Burglary/Glassbreak) receives a dedicated `switch` entity for easy bypassing.
    *   **Bypass Capability**: Support for secure bypassing and unbypassing using your panel's user code.
*   **Stored User Code**:
    *   **One-Click Action**: Optionally store your alarm code in the configuration to enable one-click Arm/Disarm without a keypad.
    *   **Security**: The code is stored locally in Home Assistant.
*   **Enriched Alarm States**:
    *   `Disarmed` / `Armed Away`
    *   `Pending`: Active Exit or Entry delay timers.
    *   `Triggered`: Active Alarm status.
*   **High Performance Architecture**:
    *   **DataUpdateCoordinator**: Centrally manages all communication in a background task to prevent UI lag.
    *   **Async/Await**: Fast, non-blocking I/O keeps Home Assistant responsive.

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
    *   Enter your **Panel IP**, **Port** (6502), and **Shared Key** (if "Basic Encryption" is enabled in AlphaTool).
    *   **(Optional) User Code**: Enter your 4-digit alarm code to enable one-click Arm/Disarm and hide the keypad in the UI.

### Existing Users (Adding User Code)
If you already have the integration installed and want to add the **User Code**, you must:
1.  Go to **Settings > Devices & Services**.
2.  **Delete** the "Alphatronics ML" integration.
3.  **Add Integration** > "UNii" again.
4.  Enter your details and the new **User Code**.
*(Note: Your entity IDs will likely remain the same, but you may need to rename them if they change.)*

## Troubleshooting

### Connection Failed (Errno 110 / WinError 121)
If you see a "Connection failed" error or the integration fails to add:
1.  **Close AlphaTool**: The panel only supports **one** connection. If AlphaTool is open, Home Assistant cannot connect.
2.  **Hard Reboot Panel**: The panel's network interface may freeze.
    *   Disconnect **AC Power** and **Battery**.
    *   Wait **10-15 seconds**.
    *   Reconnect power.

### "Arming requires a code but none was given"
If you see this error after adding your User Code:
*   **Update to v1.3.2**: A fix was released to correct how the user code is read by the buttons.
*   **Restart Home Assistant**: Ensure the new code is loaded.

## Requirements

*   **pycryptodome**: Automatically installed as a dependency.

## Acknowledgments & License

This project is an evolution of the original library and integration developed by [unii-security](https://github.com/unii-security). We have adapted the core logic into a standalone, asynchronous, and multi-entity integration for improved stability and feature coverage.

This software is licensed under the **Apache License 2.0**. See the `LICENSE` file for details.

---
**GitHub Repository**: [homeassistant-alphatronic-ml](https://github.com/andy911850/homeassistant-alphatronic-ml)
