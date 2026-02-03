import json
import os
import secrets
from typing import Dict, Any

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "server_name": "My Minecraft Server",
    "jar_path": "/path/to/server.jar",
    "java_path": "java",
    "ram_min": "1G",
    "ram_max": "2G",
    "server_dir": ".",
    "admin_password_hash": "",  # SHA256 hash
    "secret_key": secrets.token_hex(32)
}

class ConfigManager:
    def __init__(self):
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(CONFIG_FILE):
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        except Exception:
            return DEFAULT_CONFIG.copy()

    def save_config(self, new_config: Dict[str, Any]):
        self.config.update(new_config)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=4)

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save_config(self.config)

# Global instance
config = ConfigManager()
