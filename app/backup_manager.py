import tempfile
import os
import shutil
import glob
import datetime
import asyncio
from app.config import config
from app.logger import app_logger

class BackupManager:
    def __init__(self):
        self.current_status = {
            "state": "idle", # idle, running, success, error, cancelled
            "message": "",
            "progress": 0,
            "filename": ""
        }
        self.cancel_requested = False

    def get_status(self):
        return self.current_status
    
    def cancel_backup(self):
        if self.current_status["state"] == "running":
            self.cancel_requested = True
            app_logger.warning("Backup cancellation requested")
            return {"status": "success", "message": "Cancellation requested"}
        app_logger.warning("Cancel backup failed: No backup running")
        return {"status": "error", "message": "No backup running"}

    def list_backups(self):
        backup_dir = os.path.expanduser(config.get("backup_path"))
        if not os.path.exists(backup_dir):
            app_logger.debug("Backup directory does not exist")
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
        app_logger.debug(f"Listed {len(backups)} backups")
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
            app_logger.warning("Backup creation failed: Backup already running")
            return {"status": "error", "message": "Backup already running"}

        app_logger.info("=" * 60)
        app_logger.info(f"BACKUP CREATION STARTED: {backup_type}")
        if backup_type == "world":
            app_logger.info(f"World name: {world_name}")
        app_logger.info("=" * 60)
        
        if config.get("debug_mode"):
             print(f"[TRACE] BackupManager.create_backup: type={backup_type} world={world_name}")

        self.current_status = {
            "state": "running",
            "message": "Initializing...",
            "progress": 0,
            "filename": ""
        }
        self.cancel_requested = False
        
        # Fire and forget (run in thread)
        asyncio.create_task(
            asyncio.to_thread(self._create_backup_sync, backup_type, world_name)
        )
        
        return {"status": "started", "message": "Backup started"}

    def _create_backup_sync(self, backup_type, world_name):
        try:
            # ... path setup same as before ...
            server_dir = os.path.expanduser(config.get("server_dir"))
            backup_dir = os.path.expanduser(config.get("backup_path"))
            
            if not os.path.exists(backup_dir):
                os.makedirs(backup_dir, exist_ok=True)

            timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            
            if backup_type == "full":
                source_root = server_dir
                base_name = f"full_backup_{timestamp}.zip"
            else:
                source_root = os.path.join(server_dir, world_name)
                base_name = f"world_backup_{world_name}_{timestamp}.zip"
                if not os.path.exists(source_root):
                    app_logger.error(f"World folder '{world_name}' not found")
                    raise FileNotFoundError(f"World folder '{world_name}' not found.")

            app_logger.info(f"Backup source: {source_root}")
            app_logger.info(f"Backup destination: {backup_dir}")
            app_logger.info(f"Backup filename: {base_name}")

            target_zip = self._get_unique_path(backup_dir, base_name)
            
            # 1. Count files
            self.current_status["message"] = "Scanning files..."
            total_files = 0
            files_to_zip = []
            
            abs_backup_dir = os.path.abspath(backup_dir)
            
            for root, dirs, files in os.walk(source_root):
                if self.cancel_requested: raise Exception("Cancelled by user")
                
                if os.path.abspath(root).startswith(abs_backup_dir):
                    continue
                
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, server_dir if backup_type == "full" else os.path.dirname(source_root))
                    files_to_zip.append((file_path, arcname))
                    total_files += 1

            if total_files == 0:
                app_logger.error("No files found to backup")
                raise Exception("No files found")

            app_logger.info(f"Found {total_files} files to backup")

            # 2. Create Zip (Fast Mode)
            self.current_status["message"] = f"Archiving {total_files} files..."
            self.current_status["filename"] = base_name
            app_logger.info("Starting compression (level 1 - fast mode)...")
            
            fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
            os.close(fd)
            
            import zipfile
            processed = 0
            # Use ZIP_STORED for speed, ZIP_DEFLATED for size. User asked for speed.
            # ZIP_STORED is just a container, no CPU usage for compression.
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED, compresslevel=1) as zipf:
                 for file_path, arcname in files_to_zip:
                    if self.cancel_requested: raise Exception("Cancelled by user")
                    
                    zipf.write(file_path, arcname)
                    processed += 1
                    if processed % 100 == 0: # Check less often for speed
                        self.current_status["progress"] = int((processed / total_files) * 100)
                        if processed % 500 == 0:  # Log every 500 files
                            app_logger.debug(f"Compression progress: {processed}/{total_files} files ({self.current_status['progress']}%)")

            # 3. Move
            if self.cancel_requested: raise Exception("Cancelled by user")
            
            self.current_status["message"] = "Finalizing..."
            app_logger.info("Moving backup to final destination...")
            shutil.move(temp_zip_path, target_zip)
            os.chmod(target_zip, 0o644)
            
            backup_size_mb = os.path.getsize(target_zip) / (1024 * 1024)
            app_logger.info(f"✓ Backup completed successfully")
            app_logger.info(f"Backup file: {base_name}")
            app_logger.info(f"Backup size: {backup_size_mb:.2f} MB")
            app_logger.info("=" * 60)
            
            self.current_status = {
                "state": "success",
                "message": "Backup completed successfully",
                "progress": 100,
                "filename": base_name
            }
            
        except Exception as e:
            # Cleanup
            if 'temp_zip_path' in locals() and os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            
            state = "cancelled" if str(e) == "Cancelled by user" else "error"
            if state == "cancelled":
                app_logger.warning(f"Backup cancelled: {str(e)}")
            else:
                app_logger.error(f"Backup failed: {str(e)}")
            
            self.current_status = {
                "state": state,
                "message": str(e),
                "progress": 0,
                "filename": ""
            }

    def delete_backup(self, filename):
        backup_dir = os.path.expanduser(config.get("backup_path"))
        target = os.path.join(backup_dir, filename)
        
        # Security check
        if not os.path.abspath(target).startswith(os.path.abspath(backup_dir)):
             app_logger.error(f"Backup deletion denied: Invalid path attempted - {filename}")
             return {"status": "error", "message": "Invalid path"}

        if os.path.exists(target):
            file_size = os.path.getsize(target) / (1024 * 1024)
            os.remove(target)
            app_logger.info(f"Backup deleted: {filename} ({file_size:.2f} MB)")
            return {"status": "success", "message": "Backup deleted"}
        app_logger.warning(f"Backup deletion failed: File not found - {filename}")
        return {"status": "error", "message": "File not found"}

    def get_disk_usage(self):
        backup_dir = os.path.expanduser(config.get("backup_path"))
        if not os.path.exists(backup_dir):
            os.makedirs(backup_dir, exist_ok=True)
            app_logger.debug("Created backup directory")
            
        total, used, free = shutil.disk_usage(backup_dir)
        app_logger.debug(f"Disk usage - Total: {total/(2**30):.2f}GB, Used: {used/(2**30):.2f}GB, Free: {free/(2**30):.2f}GB")
        return {
            "total_gb": round(total / (2**30), 2),
            "used_gb": round(used / (2**30), 2),
            "free_gb": round(free / (2**30), 2)
        }

backup_manager = BackupManager()
