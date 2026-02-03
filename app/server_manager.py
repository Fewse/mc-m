import asyncio
import subprocess
import os
import psutil
import queue
from typing import Optional, List
from app.config import config

class ServerManager:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.console_queue = queue.Queue(maxsize=100) # Store last 100 lines
        self.listeners = [] # WebSocket listeners

    def start_server(self):
        if self.is_running():
            return {"status": "error", "message": "Server is already running"}

        jar_path = config.get("jar_path")
        if not os.path.exists(jar_path):
             return {"status": "error", "message": f"Jar file not found at {jar_path}"}
        
        server_dir = config.get("server_dir")
        if not os.path.exists(server_dir):
             os.makedirs(server_dir, exist_ok=True)

        cmd = [
            config.get("java_path", "java"),
            f"-Xms{config.get('ram_min', '1G')}",
            f"-Xmx{config.get('ram_max', '2G')}",
            "-jar",
            jar_path,
            "nogui"
        ]

        try:
            self.process = subprocess.Popen(
                cmd,
                cwd=server_dir,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1 # Line buffered
            )
            # Start background thread/task to read stdout
            return {"status": "success", "message": "Server started"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def stop_server(self):
        if not self.is_running():
            return {"status": "error", "message": "Server is not running"}
        
        self.send_command("stop")
        return {"status": "success", "message": "Stop command sent"}

    def force_kill(self):
        if self.process:
            self.process.kill()
            self.process = None
            return {"status": "success", "message": "Process killed"}
        return {"status": "error", "message": "No process to kill"}

    def is_running(self):
        if self.process is None:
            return False
        return self.process.poll() is None

    def send_command(self, cmd: str):
        if self.is_running() and self.process.stdin:
            try:
                self.process.stdin.write(cmd + "\n")
                self.process.stdin.flush()
            except IOError:
                pass

    async def read_stream_loop(self):
        """Must be scheduled as background task"""
        while True:
            if self.process and self.is_running() and self.process.stdout:
                # Blocking read, so we should run this in executor or carefully
                # Ideally, we use asyncio.create_subprocess_exec for async, 
                # but for simplicity with standard Popen we can peek.
                # Let's switch to a non-blocking read or thread.
                # Actually, standard readline() in a thread is best for Popen.
                await asyncio.sleep(0.1) # Placeholder for loop mechanism logic
                pass
            else:
                await asyncio.sleep(1)

    def get_stats(self):
        cpu = 0
        ram = 0
        status = "offline"
        
        if self.is_running():
            status = "online"
            try:
                p = psutil.Process(self.process.pid)
                with p.oneshot():
                    cpu = p.cpu_percent()
                    ram = p.memory_info().rss / 1024 / 1024 # MB
            except psutil.NoSuchProcess:
                status = "offline"
        
        return {
            "status": status,
            "cpu": cpu,
            "ram": f"{ram:.1f} MB"
        }

# For simple reading of stdout without blocking the async loop, 
# we can use a Thread to update the queue.
import threading
def reader_thread(server_manager):
    while True:
        if server_manager.process and server_manager.process.stdout:
            line = server_manager.process.stdout.readline()
            if line:
                server_manager.console_queue.put(line)
                # Notify listeners would happen here via some bridge
            else:
                if not server_manager.is_running():
                    import time
                    time.sleep(1)

server_manager = ServerManager()

# Start the reading thread
t = threading.Thread(target=reader_thread, args=(server_manager,), daemon=True)
t.start()
