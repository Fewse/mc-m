import tempfile
from app.config import config

class BackupManager:
    def __init__(self):
        self.current_status = {
            "state": "idle", # idle, running, success, error
            "message": "",
            "progress": 0,
            "filename": ""
        }

    def get_status(self):
        return self.current_status

    def list_backups(self):
        backup_dir = os.path.expanduser(config.get("backup_path"))
        if not os.path.exists(backup_dir):
            return []
        
        # List zip files
        files = glob.glob(os.path.join(backup_dir, "*.zip"))
        backups = []
        for f in files:
            try:
                stat = os.stat(f)
                backups.append({
                    "name": os.path.basename(f),
                    "size": stat.st_size,
                    "created": datetime.datetime.fromtimestamp(stat.st_mtime).isoformat()
                })
            except FileNotFoundError:
                pass
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
        if self.current_status["state"] == "running":
            return {"status": "error", "message": "Backup already running"}

        self.current_status = {
            "state": "running",
            "message": "Initializing...",
            "progress": 0,
            "filename": ""
        }
        
        # Fire and forget (run in thread)
        asyncio.create_task(
            asyncio.to_thread(self._create_backup_sync, backup_type, world_name)
        )
        
        return {"status": "started", "message": "Backup started"}

    def _create_backup_sync(self, backup_type, world_name):
        try:
            server_dir = os.path.expanduser(config.get("server_dir"))
            backup_dir = os.path.expanduser(config.get("backup_path"))
            
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            # Setup paths
            if backup_type == "full":
                source_root = server_dir
                base_name = f"full_backup_{timestamp}.zip"
            else:
                source_root = os.path.join(server_dir, world_name)
                base_name = f"world_backup_{world_name}_{timestamp}.zip"
                if not os.path.exists(source_root):
                    raise FileNotFoundError(f"World folder '{world_name}' not found.")

            target_zip = self._get_unique_path(backup_dir, base_name)
            
            # 1. Count files for progress
            self.current_status["message"] = "Scanning files..."
            total_files = 0
            files_to_zip = [] # List of (abs_path, arcname)
            
            abs_backup_dir = os.path.abspath(backup_dir)
            abs_source_root = os.path.abspath(source_root)
            
            for root, dirs, files in os.walk(source_root):
                # Avoid recursion if backing up full server and backup dir is inside
                if os.path.abspath(root).startswith(abs_backup_dir):
                    continue
                
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, server_dir if backup_type == "full" else os.path.dirname(source_root))
                    files_to_zip.append((file_path, arcname))
                    total_files += 1

            if total_files == 0:
                raise Exception("No files found to backup")

            # 2. Create Zip
            self.current_status["message"] = f"Archiving {total_files} files..."
            self.current_status["filename"] = base_name
            
            fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(fd)
            
            import zipfile
            processed = 0
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path, arcname in files_to_zip:
                    zipf.write(file_path, arcname)
                    processed += 1
                    # Update progress every 10 files or so to reduce lock contention
                    if processed % 10 == 0:
                        self.current_status["progress"] = int((processed / total_files) * 100)

            # 3. Move
            self.current_status["message"] = "Finalizing..."
            shutil.move(temp_zip_path, target_zip)
            os.chmod(target_zip, 0o644)
            
            self.current_status = {
                "state": "success",
                "message": "Backup completed successfully",
                "progress": 100,
                "filename": base_name
            }
            
        except Exception as e:
            print(f"Backup Error: {e}")
            if 'temp_zip_path' in locals() and os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            
            self.current_status = {
                "state": "error",
                "message": str(e),
                "progress": 0,
                "filename": ""
            }

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
