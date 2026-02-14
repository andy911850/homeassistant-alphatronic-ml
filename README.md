# AlphaVision Unii Custom Component

This is a standalone Home Assistant integration for AlphaVision Unii alarms, using a reverse-engineered TCP protocol (Port 6502).

## Installation

1.  Copy the `custom_components/unii` folder to your Home Assistant's `config/custom_components/` directory.
2.  Restart Home Assistant.
3.  Go to **Settings > Devices & Services**.
4.  Click **Add Integration** and search for **Unii Alarm**.
5.  Enter your Alarm IP, Port (6502), and Shared Key.

## Features
*   **Arm Away**: Arms Section 1.
*   **Disarm**: Disarms Section 1.
*   **Status**: Polls the alarm status every 30 seconds.

## Requirements
*   Encryption support is handled automatically (Python dependencies are defined in `manifest.json`).

## Acknowledgments & License

This project is a modified version of the original [homeassistant-unii](https://github.com/unii-security/homeassistant-unii) integration by `unii-security`.

This software is licensed under the **Apache License 2.0**. See the `LICENSE` file for details.

---
*Modified by andy911850 (2026)*
