import shutil
import os
import datetime
import glob
from app.config import config

class BackupManager:
    def list_backups(self):
        backup_dir = os.path.join(config.get("server_dir"), "backups")
        if not os.path.exists(backup_dir):
            return []
        
        # List zip files
        files = glob.glob(os.path.join(backup_dir, "*.zip"))
        backups = []
        for f in files:
            stat = os.stat(f)
            backups.append({
                "name": os.path.basename(f),
                "size": stat.st_size,
                "created": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
            })
        return sorted(backups, key=lambda x: x["created"], reverse=True)

    def create_backup(self, world_name="world"):
        server_dir = config.get("server_dir")
        backup_dir = os.path.join(server_dir, "backups")
        os.makedirs(backup_dir, exist_ok=True)
        
        world_path = os.path.join(server_dir, world_name)
        if not os.path.exists(world_path):
             return {"status": "error", "message": f"World folder '{world_name}' not found."}

        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"backup_{world_name}_{timestamp}"
        target_zip = os.path.join(backup_dir, filename)
        
        try:
            shutil.make_archive(target_zip, 'zip', world_path)
            return {"status": "success", "message": f"Backup created: {filename}.zip"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_backup(self, filename):
        backup_dir = os.path.join(config.get("server_dir"), "backups")
        target = os.path.join(backup_dir, filename)
        
        # Security check
        if not os.path.abspath(target).startswith(os.path.abspath(backup_dir)):
             return {"status": "error", "message": "Invalid path"}

        if os.path.exists(target):
            os.remove(target)
            return {"status": "success", "message": "Backup deleted"}
        return {"status": "error", "message": "File not found"}

backup_manager = BackupManager()
