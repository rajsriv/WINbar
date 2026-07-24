# 🪟 WaybarWin

<p align="center">
  <img src="https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-blue?style=for-the-badge&logo=windows" alt="Platform: Windows" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python Version" />
  <img src="https://img.shields.io/badge/UI%20Framework-PyQt6-41CD52?style=for-the-badge&logo=qt&logoColor=white" alt="UI Framework: PyQt6" />
  <img src="https://img.shields.io/badge/License-MIT-yellow?style=for-the-badge" alt="License: MIT" />
</p>

An elegant, highly customizable, and fluid status bar for Windows inspired by Linux's **Waybar**. Built with **PyQt6** and integrated deeply with Windows native APIs, **WaybarWin** behaves like a native desktop appbar—reserving space on your screen and providing beautiful acrylic blur effects, live system monitoring, virtual desktop integration, and interactive widgets.

---

## ✨ Features

*   **🧱 Native Windows AppBar Integration:** Registers with the Windows Shell (via `SHAppBarMessage`) to act as a desktop appbar. It docks at the top of the screen and automatically forces other windowed applications to respect its boundaries.
*   **🌀 Acrylic & Aero Blur Effects:** Integrates with Windows composition APIs (`SetWindowCompositionAttribute`) to enable modern semi-transparent blur/acrylic effects for popups and menus.
*   **💻 Virtual Desktop Workspaces:** Real-time tracking and switching of Windows 10/11 Virtual Desktops utilizing `pyvda`. Displays workspace indicators similar to iOS page dots.
*   **🎵 Media Integration (SMTC):** Connects to Windows Global System Media Transport Controls (SMTC). Fetches real-time playback state, artist details, track title, and album art thumbnail. Includes an **interactive animated wave seekbar**!
*   **📅 Dynamic Clock & Calendar Popup:** A clock widget that reveals a slick calendar dashboard with sliding animations on hover. Features a loopable circular video player.
*   **📊 System Resource Monitor:** Real-time feedback on CPU and Memory (RAM) utilization.
*   **🎨 CSS Theming System:** Includes a fully-customizable theme system supporting Dark and Light modes with custom QSS (Qt Stylesheets).

---

## 🛠️ Tech Stack & Architecture

WaybarWin is composed of several modular Python scripts:

*   [`main.py`](file:///c:/Users/raj2005sriv/Desktop/Raj%20Prsnl/skill/waybar-win/main.py): Launches the application, manages multi-display screen detection, and instantiates the bars.
*   [`bar.py`](file:///c:/Users/raj2005sriv/Desktop/Raj%20Prsnl/skill/waybar-win/bar.py): Contains the core `WaybarWindow` layout and custom widgets (`WorkspacesWidget`, `SystemMonitorWidget`, `ClockWidget`, `WaveSeekBar`, `MediaPopupWidget`).
*   [`appbar.py`](file:///c:/Users/raj2005sriv/Desktop/Raj%20Prsnl/skill/waybar-win/appbar.py): Low-level ctypes bindings for registering the window as a native Windows AppBar.
*   [`theme.py`](file:///c:/Users/raj2005sriv/Desktop/Raj%20Prsnl/skill/waybar-win/theme.py): Theme engine managing colors, styles, and stylesheet loading.
*   [`build.py`](file:///c:/Users/raj2005sriv/Desktop/Raj%20Prsnl/skill/waybar-win/build.py): PyInstaller compilation helper.

---

## 🚀 Getting Started

### Prerequisites

Make sure you have **Python 3.10+** installed. You will also need standard build tools for Python on Windows.

### Installation

1. Clone this repository:
   ```bash
   git clone https://github.com/raj2005sriv/waybar-win.git
   cd waybar-win
   ```

2. Install the required dependencies:
   ```bash
   pip install PyQt6 psutil pyvda winsdk
   ```

> [!NOTE]
> `winsdk` is required to integrate with the Windows System Media Transport Controls (SMTC) to read media titles and album art. `pyvda` requires the virtual desktop feature to be enabled on Windows.

### Running the Application

To start the status bar in development mode:
```bash
python main.py
```

To run it silently in the background (using VBS helper):
```bash
wscript run.vbs
```

---

## 📦 Compilation & Packaging

You can compile **WaybarWin** into a standalone `.exe` using **PyInstaller**. The repository includes a helper script [`build.py`](file:///c:/Users/raj2005sriv/Desktop/Raj%20Prsnl/skill/waybar-win/build.py) that packages the app windowed, cleans the build artifacts, embeds the version information, and attaches the video loop:

To compile the executable, run:
```bash
python build.py
```
The compiled output will be generated inside the `dist/WaybarWin/` directory.

---

## 🎨 Customization

You can customize the layout, colors, and font-families directly within [`theme.py`](file:///c:/Users/raj2005sriv/Desktop/Raj%20Prsnl/skill/waybar-win/theme.py):

*   **Palettes:** Adjust the `DARK_PALETTE` and `LIGHT_PALETTE` dictionaries to change font colors, backgrounds, accent colors, separators, and hover transitions.
*   **CSS Styles:** Customize stylesheets inside `get_theme_stylesheet()` using standard Qt QSS selectors.

---

## 📄 License

This project is licensed under the MIT License - see the [version_info.txt](file:///c:/Users/raj2005sriv/Desktop/Raj%20Prsnl/skill/waybar-win/version_info.txt) file or licensing headers for details.
