import shutil
import os
import datetime
import glob
from app.config import config

class BackupManager:
    def list_backups(self):
        backup_dir = os.path.expanduser(config.get("backup_path"))
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

    def _get_unique_path(self, directory, filename):
        """Ensures filename is unique by appending counter if needed"""
        name, ext = os.path.splitext(filename)
        counter = 1
        new_filename = filename
        while os.path.exists(os.path.join(directory, new_filename)):
            new_filename = f"{name}_{counter}{ext}"
            counter += 1
        return os.path.join(directory, new_filename)

    def create_backup(self, backup_type="world", world_name="world"):
        server_dir = os.path.expanduser(config.get("server_dir"))
        backup_dir = os.path.expanduser(config.get("backup_path"))
        
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
            
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        if backup_type == "full":
            # Backup entire server directory
            base_name = f"full_backup_{timestamp}.zip"
            target_zip = self._get_unique_path(backup_dir, base_name)
            
            # Helper to filter out the backup directory itself to prevent recursion loop
            def filter_backups(dirpath, contents):
                # Normalize paths for comparison
                abs_dir = os.path.abspath(dirpath)
                abs_backup = os.path.abspath(backup_dir)
                if abs_dir.startswith(abs_backup) or abs_dir == abs_backup:
                    return contents # Ignore everything in backup dir
                if abs_backup.startswith(abs_dir) and abs_backup != abs_dir:
                     # Backup dir is inside current dir, exclude it from list
                     return [os.path.basename(abs_backup)]
                return []

            try:
                # shutil.make_archive is tricky with exclusion. 
                # Using zipfile directly is safer for exclusion logic.
                import zipfile
                with zipfile.ZipFile(target_zip, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(server_dir):
                        # Skip backup dir
                        if os.path.abspath(root).startswith(os.path.abspath(backup_dir)):
                            continue
                        
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, server_dir)
                            zipf.write(file_path, arcname)
                            
                return {"status": "success", "message": f"Full backup created: {os.path.basename(target_zip)}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

        else:
            # World backup
            world_path = os.path.join(server_dir, world_name)
            if not os.path.exists(world_path):
                 return {"status": "error", "message": f"World folder '{world_name}' not found."}

            base_name = f"world_backup_{world_name}_{timestamp}.zip"
            target_zip = self._get_unique_path(backup_dir, base_name)
            
            try:
                # shutil works fine for single directory
                shutil.make_archive(target_zip.replace('.zip', ''), 'zip', world_path)
                return {"status": "success", "message": f"World backup created: {os.path.basename(target_zip)}"}
            except Exception as e:
                return {"status": "error", "message": str(e)}

    def delete_backup(self, filename):
        backup_dir = os.path.expanduser(config.get("backup_path"))
        target = os.path.join(backup_dir, filename)
        
        # Security check
        if not os.path.abspath(target).startswith(os.path.abspath(backup_dir)):
             return {"status": "error", "message": "Invalid path"}

        if os.path.exists(target):
            os.remove(target)
            return {"status": "success", "message": "Backup deleted"}
        return {"status": "error", "message": "File not found"}

backup_manager = BackupManager()
