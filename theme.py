from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor

DARK_PALETTE = {
    "name": "Dark",
    "text": "#ffffff",
    "text_muted": "#808080",
    "text_darker": "#a0a0a0",
    "bg": "#1e1e1e",
    "bg_transparent": "rgba(30, 30, 30, 0.94)",
    "bg_bar": "rgba(15, 15, 15, 0.55)",
    "workspace_text": "#cdd6f4",
    "workspace_dot": "rgba(255, 255, 255, 0.25)",
    "accent": "#89b4fa",
    "accent_hover": "rgba(137, 180, 250, 0.2)",
    "separator": "#333333",
    "media_bg": "rgba(255, 255, 255, 0.15)",
    "media_bg_hover": "rgba(255, 255, 255, 0.25)",
    "media_time": "#e0e0e0",
    "shadow": "rgba(0, 0, 0, 150)",
    "shadow_darker": "rgba(0, 0, 0, 200)",
    "capsule_bg": "rgba(30, 30, 30, 0.55)",
    "sys_chart_bg": "#1e1e1e",
    "sys_chart_border": "rgba(255, 255, 255, 80)",
    "sys_chart_fill": "rgba(255, 255, 255, 40)"
}

LIGHT_PALETTE = {
    "name": "Light",
    "text": "#1a1a1a",
    "text_muted": "#606060",
    "text_darker": "#505050",
    "bg": "#f0f0f0",
    "bg_transparent": "rgba(240, 240, 240, 0.94)",
    "bg_bar": "rgba(255, 255, 255, 0.15)",
    "workspace_text": "#4c4f69",
    "workspace_dot": "rgba(0, 0, 0, 0.2)",
    "accent": "#1e66f5",
    "accent_hover": "rgba(30, 102, 245, 0.2)",
    "separator": "#d0d0d0",
    "media_bg": "rgba(0, 0, 0, 0.1)",
    "media_bg_hover": "rgba(0, 0, 0, 0.2)",
    "media_time": "#404040",
    "shadow": "rgba(0, 0, 0, 50)",
    "shadow_darker": "rgba(0, 0, 0, 80)",
    "capsule_bg": "rgba(255, 255, 255, 0.55)",
    "sys_chart_bg": "#ffffff",
    "sys_chart_border": "rgba(0, 0, 0, 60)",
    "sys_chart_fill": "rgba(0, 0, 0, 30)"
}

def get_windows_accent_color():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r'Software\Microsoft\Windows\DWM')
        val, _ = winreg.QueryValueEx(key, 'ColorizationColor')
        winreg.CloseKey(key)
        
        r = (val >> 16) & 0xFF
        g = (val >> 8) & 0xFF
        b = val & 0xFF
        return r, g, b
    except:
        return 0, 120, 212

def hex_to_qcolor(hex_str):
    if hex_str.startswith("rgba"):
        import re
        match = re.search(r"rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)", hex_str)
        if match:
            r, g, b, a = match.groups()
            alpha = float(a)
            if alpha <= 1.0: alpha = int(alpha * 255)
            else: alpha = int(alpha)
            return QColor(int(r), int(g), int(b), alpha)
    return QColor(hex_str)

def get_theme_stylesheet(palette):
    return f"""
* {{
    font-family: "SF Pro Display", "-apple-system", "BlinkMacSystemFont", "SF Pro Text", "Segoe UI", "Inter", sans-serif;
    font-size: 12px;
    color: {palette["text"]};
}}

#main-window {{
    background-color: {palette["bg_bar"]};
    border-bottom: none;
}}

QFrame {{
    background-color: transparent;
    border-radius: 0px;
}}

/* Workspaces as iOS Page Indicator Dots */
#workspaces QPushButton {{
    background-color: {palette["workspace_dot"]};
    border: none;
    min-width: 8px;
    max-width: 8px;
    min-height: 8px;
    max-height: 8px;
    border-radius: 4px;
    padding: 0;
    margin: 0 4px;
    font-size: 0px;
}}

#workspaces QPushButton:checked {{
    background-color: {palette["text"]};
}}

#workspaces QPushButton:hover {{
    background-color: {palette["accent"]};
}}

/* Clock */
#clock {{
    background-color: transparent;
}}

/* Media */
#media, #sys-monitor {{
    background-color: transparent;
}}

/* Right Modules */
#modules-right QLabel {{
    margin: 0 5px;
}}

#modules-right QPushButton {{
    font-family: "Segoe MDL2 Assets";
    font-size: 16px;
    background-color: transparent;
    border: none;
    padding: 0;
    margin: 0 5px;
    color: {palette["text"]};
}}

#modules-right QPushButton:hover {{
    color: {palette["accent"]};
}}

/* Media Popup */
#media-popup-container {{
    background-color: transparent;
    border-radius: 20px;
}}

#media-title {{
    font-weight: bold;
    font-size: 12px;
}}

#media-time {{
    font-size: 10px;
    color: {palette["media_time"]};
}}

#media-popup-container QPushButton {{
    font-family: "Segoe MDL2 Assets";
    font-size: 14px;
    background-color: transparent;
    border: none;
    color: {palette["text"]};
    padding: 3px;
    margin: 0 2px;
}}

#media-play-btn {{
    background-color: {palette["media_bg"]} !important;
    border-radius: 8px !important;
    font-size: 16px !important;
}}

#media-popup-container QPushButton:hover {{
    background-color: {palette["media_bg_hover"]} !important;
}}
"""

def get_theme():
    from config import load_style
    custom_style = load_style()
    settings = QSettings("WaybarWin", "Settings")
    theme_name = settings.value("theme", "Dark", type=str)
    popup_style = settings.value("popup_style", "popup", type=str)
    
    if theme_name == "Light":
        pal = dict(LIGHT_PALETTE)
    else:
        pal = dict(DARK_PALETTE)
        
    if popup_style in ["edgeBox", "edgeCurve"]:
        pal["bg_bar"] = "rgba(0, 0, 0, 1.0)"
        pal["capsule_bg"] = "rgba(0, 0, 0, 1.0)"
        
    return pal, get_theme_stylesheet(pal) + "\n" + custom_style
