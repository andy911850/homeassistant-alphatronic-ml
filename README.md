# Alphatronics ML / UNii (Custom Component)

This is a specialized Home Assistant integration designed for **Alphatronics ML** and **UNii** alarm systems. 
It communicates via the local network (Port 6502) using a reverse-engineered binary protocol, specifically optimized for the **ML Series** panels.

**Current Version: v2.0.3**

## Key Features

*   **⚡ Optimistic UI**: Instant feedback for Arm/Disarm operations, providing a snappy user experience.
*   **🔒 Full Arm/Disarm Support**:
    *   Arm and disarm individual sections or all sections via the Master panel.
    *   Protocol-correct payload format matching the official [py-unii](https://github.com/unii-security/py-unii) library.
*   **🛡️ Bypass Control**:
    *   Bypass and unbypass individual inputs (zones) directly from Home Assistant.
    *   Uses the standard 16-digit/8-byte BCD protocol for full compatibility.
*   **📊 Accurate Monitoring**:
    *   **Smart State Detection**: Correctly identifies Open/Closed states using bit-level status analysis (Alarm, Tamper, Masking, Trouble).
    *   **Auto-Filtering**: Automatically hides disabled inputs (status `0x0F`) and empty "VRIJE TEKST" zones to keep your dashboard clean.
*   **🔌 Stability First**:
    *   **Persistent Connection**: Maintains a single TCP connection with automatic reconnection on failure.
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

## Write Access (Arm/Disarm/Bypass)

To enable arming, disarming, and bypass operations, you must configure a **User Code**:

1.  Go to **Settings > Devices & Services > UNii > Configure**.
2.  Enter your alarm **User Code** (e.g., `989898`).
3.  The User Code must have **Level 7 (Engineer/Manager)** permissions for all operations.
4.  A **6-digit code** is recommended due to firmware requirements.

## Troubleshooting

### Connection Failed
If you see a "Connection failed" error:
1.  **Close AlphaTool**: The panel only supports **one** connection.
2.  **Hard Reboot Panel**: Disconnect AC and Battery for 15 seconds if the interface is frozen.

### Arm/Disarm Not Working
1.  Ensure you have entered a valid **User Code** in the integration configuration.
2.  Check that the User Code has sufficient permissions on the panel.
3.  If only one section arms when using Master, verify all sections are configured as active in AlphaTool.

### Bypass Switch Issues
1.  Ensure you have entered a **User Code** in the integration configuration.
2.  The User Code must have **Level 7** permissions to perform bypass operations.

## Changelog

### v2.0.3
*   **Fixed**: Arm/disarm payload corrected to use 1-byte Section ID (matching official py-unii protocol). Previous 2-byte format caused the panel to silently ignore commands.
*   **Fixed**: Restored input filtering for disabled inputs (status `0x0F`).

### v2.0.2
*   **Fixed**: Restored missing arm/disarm methods after v2.0 refactor.

### v2.0.0
*   **New**: Full codebase refactor with clean polling architecture.
*   **New**: Persistent TCP connection with automatic reconnection.
*   **New**: Master alarm panel entity for arming/disarming all sections at once.
*   **New**: Type-0 sensor discovery (Woonkamer, Keuken, etc.).
*   **Improved**: Optimistic UI for bypass operations.

## Acknowledgments & License

This project is an evolution of the original library and integration developed by [unii-security](https://github.com/unii-security).
Licensed under the **Apache License 2.0**.
