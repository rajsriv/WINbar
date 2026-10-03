import os
import yaml

CONFIG_DIR = os.path.expanduser("~/.config/winbar")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.yaml")
STYLE_FILE = os.path.join(CONFIG_DIR, "style.qss")

DEFAULT_CONFIG = {
    "general": {
        "layer": "top",
        "position": "top",
        "height": 37
    },
    "layout": {
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
            "modules-right" # this looks like a typo in original config but keeping it
        ]
    },
    "displays": {
        "enabled_monitors": []
    },
    "style": {
        "popup_style": "popup"
    }
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
                yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)
            return DEFAULT_CONFIG
        except Exception as e:
            print(f"Failed to write default config: {e}")
            return DEFAULT_CONFIG
            
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            user_config = yaml.safe_load(f) or {}
            
            # Merge missing keys from default config (2 levels deep for our structure)
            for section, values in DEFAULT_CONFIG.items():
                if section not in user_config:
                    user_config[section] = values
                elif isinstance(values, dict) and isinstance(user_config[section], dict):
                    for k, v in values.items():
                        if k not in user_config[section]:
                            user_config[section][k] = v
                            
            # Enforce popup_style=edgeBox for left/right/bottom positions if it's set to popup
            position = user_config.get("general", {}).get("position", "top").lower()
            if position != "top":
                current_style = user_config.get("style", {}).get("popup_style", "")
                if current_style == "popup" or current_style == "":
                    if "style" not in user_config:
                        user_config["style"] = {}
                    user_config["style"]["popup_style"] = "edgeBox"
                
            return user_config
    except Exception as e:
        print(f"Failed to load config: {e}")
        return DEFAULT_CONFIG

def save_config(config):
    try:
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        print(f"Failed to save config: {e}")

def load_style():
    if not os.path.exists(STYLE_FILE):
        return ""
    try:
        with open(STYLE_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Failed to load custom style: {e}")
        return ""

def restore_defaults():
    try:
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            yaml.dump(DEFAULT_CONFIG, f, default_flow_style=False, sort_keys=False)
        return DEFAULT_CONFIG
    except Exception as e:
        print(f"Failed to restore default config: {e}")
        return DEFAULT_CONFIG
