import os
import json

CONFIG_DIR = os.path.expanduser("~/.config/winbar")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")
STYLE_FILE = os.path.join(CONFIG_DIR, "style.qss")

DEFAULT_CONFIG = {
    "layer": "top",
    "position": "top",
    "height": 37,
    "modules-left": [
        "clock",
        "workspaces",
        "launcher"
    ],
    "modules-center": [
        "taskbar",
        "media"
    ],
    "modules-right": [
        "system-monitor",
        "modules-right"
    ]
}

def load_config():
    if not os.path.exists(CONFIG_DIR):
        try:
            os.makedirs(CONFIG_DIR, exist_ok=True)
        except Exception as e:
            print(f"Failed to create config directory: {e}")
            
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=4)
            return DEFAULT_CONFIG
        except Exception as e:
            print(f"Failed to write default config: {e}")
            return DEFAULT_CONFIG
            
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = json.load(f)
            # Merge missing keys from default config
            for k, v in DEFAULT_CONFIG.items():
                if k not in user_config:
                    user_config[k] = v
            return user_config
    except Exception as e:
        print(f"Failed to load config: {e}")
        return DEFAULT_CONFIG

def load_style():
    if not os.path.exists(STYLE_FILE):
        return ""
    try:
        with open(STYLE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Failed to load custom style: {e}")
        return ""
