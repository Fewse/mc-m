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
    "backup_path": "./backups",
    "admin_password_hash": "",  # SHA256 hash
    "secret_key": secrets.token_hex(32),
    "debug_mode": False
}

class ConfigManager:
    def __init__(self):
        self.config = {}
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        if not os.path.exists(CONFIG_FILE):
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
        
        try:
            with open(CONFIG_FILE, 'r') as f:
                data = json.load(f)
                # Merge with default to ensure new keys (like debug_mode) are present
                c = DEFAULT_CONFIG.copy()
                c.update(data)
                return c
        except Exception:
            return DEFAULT_CONFIG.copy()

    def save_config(self, new_config: Dict[str, Any]):
        self.config.update(new_config)
        
        # Atomic write
        import tempfile
        tmp_fd, tmp_path = tempfile.mkstemp(dir=os.path.dirname(os.path.abspath(CONFIG_FILE)), text=True)
        try:
            with os.fdopen(tmp_fd, 'w') as f:
                json.dump(self.config, f, indent=4)
            os.replace(tmp_path, CONFIG_FILE)
        except Exception as e:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
            print(f"[ERROR] Failed to save config: {e}")

    def get(self, key: str, default=None):
        return self.config.get(key, default)

    def set(self, key: str, value: Any):
        self.config[key] = value
        self.save_config(self.config)

# Global instance
config = ConfigManager()
