import shutil
import os
import datetime
import glob
import asyncio
import tempfile
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

    async def create_backup(self, backup_type="world", world_name="world"):
        server_dir = os.path.expanduser(config.get("server_dir"))
        backup_dir = os.path.expanduser(config.get("backup_path"))
        
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
            
        return await asyncio.to_thread(self._create_backup_sync, server_dir, backup_dir, backup_type, world_name)

    def _create_backup_sync(self, server_dir, backup_dir, backup_type, world_name):
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Determine source and target name
        if backup_type == "full":
            source_path = server_dir
            base_name = f"full_backup_{timestamp}.zip"
        else:
            source_path = os.path.join(server_dir, world_name)
            base_name = f"world_backup_{world_name}_{timestamp}.zip"
            if not os.path.exists(source_path):
                 return {"status": "error", "message": f"World folder '{world_name}' not found."}

        target_zip = self._get_unique_path(backup_dir, base_name)
        
        # Use a temporary file for the zip creation to avoid:
        # 1. Recursive zipping (zipping the file being written)
        # 2. Corrupt partial files in backup dir on failure
        fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(fd) # Close the file descriptor, we just need the path

        try:
            if backup_type == "full":
                # For full backup, zip everything but exclude the backup_dir if it's inside server_dir
                import zipfile
                with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                    for root, dirs, files in os.walk(server_dir):
                        # Absolute paths for comparison
                        abs_root = os.path.abspath(root)
                        abs_backup_dir = os.path.abspath(backup_dir)
                        
                        # Exclude the backup directory itself
                        if abs_root.startswith(abs_backup_dir):
                            continue
                            
                        for file in files:
                            file_path = os.path.join(root, file)
                            # EXCLUDE the temp zip file itself (shouldn't be needed if in /tmp, but safety first)
                            if os.path.abspath(file_path) == os.path.abspath(temp_zip_path):
                                continue
                                
                            arcname = os.path.relpath(file_path, server_dir)
                            zipf.write(file_path, arcname)
            else:
                # For world, shutil is fine as we write to /tmp
                shutil.make_archive(temp_zip_path.replace('.zip', ''), 'zip', source_path)

            # Move successful backup to final location
            shutil.move(temp_zip_path, target_zip)
            
            # chmod proper permissions
            os.chmod(target_zip, 0o644)
            
            size_mb = os.path.getsize(target_zip) / (1024 * 1024)
            return {"status": "success", "message": f"Backup created: {os.path.basename(target_zip)} ({size_mb:.2f} MB)"}
            
        except Exception as e:
            # Cleanup temp file on failure
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            print(f"[ERROR] Backup failed: {e}")
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

    def get_disk_usage(self):
        backup_dir = os.path.expanduser(config.get("backup_path"))
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
            
        total, used, free = shutil.disk_usage(backup_dir)
        return {
            "total_gb": round(total / (2**30), 2),
            "used_gb": round(used / (2**30), 2),
            "free_gb": round(free / (2**30), 2)
        }

backup_manager = BackupManager()
