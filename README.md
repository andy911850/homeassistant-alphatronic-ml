# Alphatronics UNii (Custom Component)

This is a standalone, performance-optimized Home Assistant custom component for the **Alphatronics UNii** alarm system. It communicates via the local network (Port 6502) using a reverse-engineered binary protocol with AES-CTR encryption support.

## v1.1.0 Features

*   **Multi-Section Support**: Control individual alarm sections (e.g., Section 1, Section 2) independently.
*   **Master Control**: A composite Alarm Control Panel entity that monitors and controls the entire system.
*   **Zone Binary Sensors**: Real-time monitoring of all system inputs (zones).
    *   **States**: Clear, Open.
    *   **Diagnostics**: Tamper detection, Anti-masking status, and Low Battery alerts.
*   **Enriched Alarm States**: Detailed feedback for system states:
    *   `Disarmed` / `Armed Away`
    *   `Pending`: Active Exit or Entry delay timers.
    *   `Triggered`: Active Alarm status.
*   **Bypass Capability**: Support for bypassing and unbypassing inputs (zones) with a user code.
*   **High Performance Architecture**:
    *   **DataUpdateCoordinator**: Centrally manages all communication in a background task.
    *   **Parallel Polling**: Fetches section and input statuses concurrently every 5 seconds.
    *   **Async/Await**: Non-blocking I/O ensures Home Assistant remains responsive.

## Installation

1.  **HACS (Recommended)**:
    *   Add this repository as a **Custom Repository** in HACS.
    *   Install the **Alphatronics UNii (Custom)** integration.
2.  **Manual**:
    *   Copy the `custom_components/unii` folder to your Home Assistant's `config/custom_components/` directory.
3.  **Restart**: Restart Home Assistant to load the new component.
4.  **Setup**:
    *   Go to **Settings > Devices & Services**.
    *   Click **Add Integration** and search for **UNii**.
    *   Enter your **Panel IP**, **Port** (6502), and **Shared Key** (if encryption is enabled).

## Requirements

*   **pycryptodome**: Automatically installed as a dependency.

## Acknowledgments & License

This project is an evolution of the original library and integration developed by [unii-security](https://github.com/unii-security). We have adapted the core logic into a standalone, asynchronous, and multi-entity integration for improved stability and feature coverage.

This software is licensed under the **Apache License 2.0**. See the `LICENSE` file for details.

---
Current repository is: [homeassistant-alphatronic-ml](https://github.com/andy911850/homeassistant-alphatronic-ml)
