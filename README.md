# Alphatronics UNii (Custom Component)

This is a standalone, performance-optimized Home Assistant custom component for the **Alphatronics UNii** alarm system. It communicates via the local network (Port 6502) using a reverse-engineered binary protocol with AES-CTR encryption support.

## v1.2.3 Features

*   **Robust Protocol**: Corrected implementation of the UNii communication protocol (Input Arrangement), ensuring reliable connection even with complex panel configurations.
*   **Multi-Section Support**: Control individual alarm sections (e.g., Section 1, Section 2) independently.
*   **Master Control**: A composite Alarm Control Panel entity that monitors and controls the entire system.
*   **Intelligent Zone Monitoring**:
    *   **Automatic Naming**: Zones automatically use the names programmed on your UNii panel (e.g., "Hallway PIR").
    *   **Strict Filtering**: Only active, security-relevant zones are shown. Diagnostic, technical, and unprogrammed slots are automatically hidden.
    *   **States**: Clear, Open, Bypassed.
    *   **Diagnostics**: Tamper detection, Anti-masking status, and Low Battery alerts.
*   **Bypass Switches**: 
    *   **Dedicated Platform**: Each security-relevant zone (Burglary/Glassbreak) receives a dedicated `switch` entity for easy bypassing.
    *   **Bypass Capability**: Support for secure bypassing and unbypassing using your panel's user code.
*   **Enriched Alarm States**:
    *   `Disarmed` / `Armed Away`
    *   `Pending`: Active Exit or Entry delay timers.
    *   `Triggered`: Active Alarm status.
*   **High Performance Architecture**:
    *   **DataUpdateCoordinator**: Centrally manages all communication in a background task to prevent UI lag.
    *   **Async/Await**: Fast, non-blocking I/O keeps Home Assistant responsive.

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

## Requirements

*   **pycryptodome**: Automatically installed as a dependency.

## Acknowledgments & License

This project is an evolution of the original library and integration developed by [unii-security](https://github.com/unii-security). We have adapted the core logic into a standalone, asynchronous, and multi-entity integration for improved stability and feature coverage.

This software is licensed under the **Apache License 2.0**. See the `LICENSE` file for details.

---
**GitHub Repository**: [homeassistant-alphatronic-ml](https://github.com/andy911850/homeassistant-alphatronic-ml)
