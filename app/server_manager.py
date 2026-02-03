import asyncio
import subprocess
import os
import psutil
import queue
import time
import re
from collections import deque
from typing import Optional, List
from app.config import config
from app.logger import app_logger

class ServerManager:
    def __init__(self):
        self.process: Optional[subprocess.Popen] = None
        self.log_history = deque(maxlen=200) # Store last 200 lines for history
        self.publish_queue = queue.Queue() # Unbounded queue for inter-thread communication
        self.listeners = [] # WebSocket listeners
        self.pid_file = os.path.join(config.get("server_dir"), "server.pid")
        self.external_pid: Optional[int] = None
        self.external_pid: Optional[int] = None
        self.server_start_time: Optional[float] = None  # Track when server started
        self.players: dict = {}  # Track online players: {username: join_time}

        self._check_orphan()

    def _check_orphan(self):
        """Check if a server is already running from a previous session"""
        app_logger.debug(f"Checking for orphaned server process at {self.pid_file}")
        if config.get("debug_mode"): print(f"[TRACE] _check_orphan: checking {self.pid_file}")
        
        if os.path.exists(self.pid_file):
            try:
                with open(self.pid_file, 'r') as f:
                    pid = int(f.read().strip())
                
                app_logger.info(f"Found PID file with process ID: {pid}")
                if config.get("debug_mode"): print(f"[TRACE] _check_orphan: PID file found, pid={pid}")

                if psutil.pid_exists(pid):
                    try:
                        p = psutil.Process(pid)
                        # Optional: check if it looks like java/minecraft
                        if p.status() != psutil.STATUS_ZOMBIE:
                            app_logger.info(f"Adopting orphaned server process (PID: {pid})")
                            print(f"[INFO] Found orphaned server process {pid}. Adopting...")
                            self.external_pid = pid
                            self.log_history.append(f"[SYSTEM] Reconnected to running server (PID {pid}). Console input not available.")
                    except Exception as e:
                        app_logger.warning(f"Error checking orphan process: {e}")
                        if config.get("debug_mode"): print(f"[TRACE] _check_orphan logic error: {e}")
                        pass
                else:
                    app_logger.info(f"PID {pid} is dead, cleaning up stale PID file")
                    if config.get("debug_mode"): print(f"[TRACE] _check_orphan: PID {pid} is dead. Cleaning up.")
                    # Stale PID file
                    os.remove(self.pid_file)
            except Exception as e:
                app_logger.error(f"Error reading PID file: {e}")
                if config.get("debug_mode"): print(f"[TRACE] _check_orphan: Read error: {e}")
                pass


    def start_server(self):
        app_logger.info("=" * 60)
        app_logger.info("SERVER START REQUESTED")
        app_logger.info("=" * 60)
        if config.get("debug_mode"):
             app_logger.log(f"[TRACE] start_server called. Current State: {self.is_running()}")

        if self.is_running():
            app_logger.warning("Server start aborted: Server is already running")
            app_logger.log(f"[TRACE] Server already running.")
            return {"status": "error", "message": "Server is already running"}

        # Expand paths (handle ~)
        jar_path = os.path.expanduser(config.get("jar_path"))
        server_dir = os.path.expanduser(config.get("server_dir"))
        java_path = os.path.expanduser(config.get("java_path", "java"))

        app_logger.info("Starting Minecraft server...")
        app_logger.info(f"Server JAR:     {jar_path}")
        app_logger.info(f"Server Dir:     {server_dir}")
        app_logger.info(f"Java Path:      {java_path}")
        app_logger.info(f"RAM Min:        {config.get('ram_min', '1G')}")
        app_logger.info(f"RAM Max:        {config.get('ram_max', '2G')}")

        if not os.path.exists(jar_path):
             app_logger.error(f"Server JAR not found at {jar_path}")
             return {"status": "error", "message": f"Jar file not found at {jar_path}"}
        
        if not os.path.exists(server_dir):
             app_logger.info(f"Creating server directory: {server_dir}")
             os.makedirs(server_dir, exist_ok=True)

        cmd = [
            java_path,
            f"-Xms{config.get('ram_min', '1G')}",
            f"-Xmx{config.get('ram_max', '2G')}",
            "-jar",
            jar_path,
            "nogui"
        ]
        
        app_logger.debug(f"Executing command: {' '.join(cmd)}")

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
            
            # Save PID
            self.external_pid = None
            try:
                with open(self.pid_file, 'w') as f:
                    f.write(str(self.process.pid))
                app_logger.info(f"PID file created: {self.pid_file}")
            except Exception as e:
                app_logger.warning(f"Failed to write PID file: {e}")

            # Immediate post-start verification
            app_logger.info(f"✓ Server process started successfully (PID: {self.process.pid})")
            self.server_start_time = time.time()  # Track start time for uptime
            
            # Debug: Check process immediately after start
            import time
            time.sleep(0.1)  # Brief pause to let process initialize
            poll_result = self.process.poll()
            app_logger.debug(f"Post-start check: poll()={poll_result}, stdout={self.process.stdout is not None}, stdin={self.process.stdin is not None}")
            
            if poll_result is not None:
                app_logger.error(f"Process exited immediately with code: {poll_result}")
                # Try to read any error output
                try:
                    remaining_output = self.process.stdout.read()
                    if remaining_output:
                        app_logger.error(f"Process output: {remaining_output}")
                except:
                    pass
            
            app_logger.info("=" * 60)
            return {"status": "success", "message": "Server started"}
        except Exception as e:
            app_logger.error(f"Failed to start server process: {e}")
            return {"status": "error", "message": str(e)}

    async def stop_server(self):
        app_logger.info("=" * 60)
        app_logger.info("SERVER STOP REQUESTED")
        app_logger.info("=" * 60)
        if config.get("debug_mode"):
             print(f"[TRACE] stop_server called.")

        if not self.is_running():
            app_logger.warning("Server stop aborted: Server is not running")
            print(f"[TRACE] stop_server: Server not running.")
            return {"status": "error", "message": "Server is not running"}
        
        app_logger.info("Sending 'stop' command to server...")
        print(f"[TRACE] stop_server: Sending stop command.")
        self.send_command("stop")
        
        # Wait for graceful shutdown
        for i in range(20): # Wait up to 10 seconds
            if not self.is_running():
                app_logger.info(f"✓ Server stopped gracefully after {i*0.5}s")
                app_logger.info("=" * 60)
                print(f"[TRACE] stop_server: Server stopped gracefully after {i*0.5}s.")
                return {"status": "success", "message": "Server stopped gracefully"}
            await asyncio.sleep(0.5)
        
        app_logger.warning("Server did not stop within timeout period (10s)")
        print(f"[TRACE] stop_server: Timed out waiting for stop.")
        
        # Fallback if external PID and command didn't work (no stdin)
        if self.external_pid and psutil.pid_exists(self.external_pid):
             app_logger.warning(f"Cannot stop orphaned server (PID: {self.external_pid}) - no console access")
             return {"status": "warning", "message": "Cannot stop orphaned server gracefully (no console access). Use Kill."}

        return {"status": "warning", "message": "Stop command sent, but server is still running. Use Kill if needed."}

    async def restart_server(self):
        """Restart the server by stopping then starting it"""
        app_logger.info("=" * 60)
        app_logger.info("SERVER RESTART REQUESTED")
        app_logger.info("=" * 60)
        
        if not self.is_running():
            app_logger.warning("Server restart aborted: Server is not running, starting instead")
            return self.start_server()
        
        # Stop the server first
        app_logger.info("Step 1/2: Stopping server...")
        stop_result = await self.stop_server()
        
        if stop_result["status"] == "error":
            app_logger.error("Restart failed: Could not stop server")
            return {"status": "error", "message": "Failed to stop server for restart"}
        
        # Wait a moment to ensure clean shutdown
        app_logger.info("Waiting 2 seconds before restart...")
        await asyncio.sleep(2)
        
        # Start the server
        app_logger.info("Step 2/2: Starting server...")
        start_result = self.start_server()
        
        if start_result["status"] == "success":
            app_logger.info("✓ Server restarted successfully")
            app_logger.info("=" * 60)
            return {"status": "success", "message": "Server restarted successfully"}
        else:
            app_logger.error(f"Restart failed: Could not start server - {start_result.get('message')}")
            return {"status": "error", "message": f"Failed to start server after stop: {start_result.get('message')}"}

    def force_kill(self):
        app_logger.warning("FORCE KILL requested")
        if config.get("debug_mode"):
             print(f"[TRACE] force_kill called.")
             
        pid = self.external_pid
        if self.process:
            pid = self.process.pid
            self.process.kill()
            self.process = None
            app_logger.warning(f"Subprocess killed (PID: {pid})")
            print(f"[TRACE] force_kill: Killed subprocess {pid}.")
        elif self.external_pid:
            try:
                os.kill(self.external_pid, 9) # SIGKILL
                app_logger.warning(f"External process killed with SIGKILL (PID: {self.external_pid})")
                print(f"[TRACE] force_kill: Sigkilled external pid {self.external_pid}.")
            except ProcessLookupError:
                app_logger.info(f"External process {self.external_pid} already terminated")
                print(f"[TRACE] force_kill: External pid {self.external_pid} not found (already gone).")
                pass
            self.external_pid = None
        
        # Clean PID file
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
                app_logger.info("PID file cleaned up")
            except: pass

        if pid:
            return {"status": "success", "message": "Process killed"}
        app_logger.warning("No process to kill")
        return {"status": "error", "message": "No process to kill"}

    def is_running(self):
        if self.process:
            poll_result = self.process.poll()
            if config.get("debug_mode"):
                app_logger.debug(f"is_running check: self.process exists, poll()={poll_result}")
            if poll_result is None:
                return True
            # Clean up if just exited
            if config.get("debug_mode"):
                app_logger.debug(f"Process exited with code {poll_result}, cleaning up")
            self._clean_pid_file()
            return False
            
        if self.external_pid:
            if config.get("debug_mode"):
                app_logger.debug(f"is_running check: external_pid={self.external_pid}")
            if psutil.pid_exists(self.external_pid):
                 # Verify it's not a zombie
                 try:
                    proc_status = psutil.Process(self.external_pid).status()
                    if config.get("debug_mode"):
                        app_logger.debug(f"External process status: {proc_status}")
                    if proc_status == psutil.STATUS_ZOMBIE:
                        self.external_pid = None
                        self._clean_pid_file()
                        return False
                    return True
                 except psutil.NoSuchProcess:
                    if config.get("debug_mode"):
                        app_logger.debug(f"External process {self.external_pid} no longer exists")
                    self.external_pid = None
                    self._clean_pid_file()
                    return False
            self.external_pid = None
            self._clean_pid_file()
            return False
            
        if config.get("debug_mode"):
            app_logger.debug("is_running check: no process or external_pid")
        return False
        
    def _clean_pid_file(self):
        if os.path.exists(self.pid_file):
            try:
                os.remove(self.pid_file)
            except: pass

    def send_command(self, cmd: str):
        if self.process and self.process.stdin:
            try:
                app_logger.info(f"Sending command to server: {cmd}")
                if config.get("debug_mode"): print(f"[TRACE] send_command: Writing '{cmd}' to stdin.")
                self.process.stdin.write(cmd + "\n")
                self.process.stdin.flush()
            except IOError as e:
                app_logger.error(f"Failed to send command '{cmd}': {e}")
                if config.get("debug_mode"): print(f"[ERROR] send_command: IOError {e}")
                pass
        elif self.external_pid:
             app_logger.warning(f"Cannot send command '{cmd}' to orphaned process {self.external_pid}")
             print(f"[WARN] Cannot send command '{cmd}' to orphaned process {self.external_pid}")
        else:
             app_logger.debug(f"Command '{cmd}' ignored - no active process")
             if config.get("debug_mode"): print(f"[TRACE] send_command: Ignored '{cmd}', no process attached.")

    def get_players(self):
        """Get list of currently online players"""
        return list(self.players.keys())

    def get_stats(self):
        # ALWAYS log - not behind debug mode
        app_logger.info("get_stats() called")
        
        cpu = 0
        ram = 0
        status = "offline"
        
        pid = None
        if self.process:
            pid = self.process.pid
            app_logger.info(f"get_stats: Using self.process.pid={pid}")
        elif self.external_pid:
            pid = self.external_pid
            app_logger.info(f"get_stats: Using external_pid={pid}")
        else:
            app_logger.info("get_stats: No PID available (no process or external_pid)")

        if pid:
            is_running_result = self.is_running()
            app_logger.info(f"get_stats: PID={pid}, is_running()={is_running_result}")
            
            if is_running_result:
                status = "online"
                try:
                    pid_exists = psutil.pid_exists(pid)
                    if config.get("debug_mode"):
                        app_logger.debug(f"get_stats: psutil.pid_exists({pid})={pid_exists}")
                    
                    p = psutil.Process(pid)
                    with p.oneshot():
                        cpu = p.cpu_percent()
                        ram = p.memory_info().rss / 1024 / 1024 # MB
                    app_logger.debug(f"Stats collected - CPU: {cpu}%, RAM: {ram:.1f}MB")
                except psutil.NoSuchProcess:
                    status = "offline"
                    app_logger.debug("Stats: Process no longer exists (NoSuchProcess)")
                except Exception as e:
                    app_logger.error(f"Failed to collect stats: {e}")
                    print(f"[ERROR] get_stats failed: {e}")
                    pass
        
        # Calculate uptime
        uptime = "N/A"
        if status == "online" and self.server_start_time:
            uptime_seconds = int(time.time() - self.server_start_time)
            days = uptime_seconds // 86400
            hours = (uptime_seconds % 86400) // 3600
            minutes = (uptime_seconds % 3600) // 60
            
            if days > 0:
                uptime = f"{days}d {hours}h {minutes}m"
            elif hours > 0:
                uptime = f"{hours}h {minutes}m"
            else:
                uptime = f"{minutes}m"
        
        result = {
            "status": status,
            "cpu": cpu,
            "ram": f"{ram:.1f} MB",
            "uptime": uptime
        }
        app_logger.info(f"get_stats() returning: {result}")
        return result

# For simple reading of stdout without blocking the async loop, 
# we can use a Thread to update the queue.
import threading
import time

def reader_thread(server_manager):
    app_logger.info("Server output reader thread started")
    app_logger.log(f"[TRACE] reader_thread: Started.")
    last_process_state = None
    
    while True:
        try:
            has_process = server_manager.process is not None
            has_stdout = server_manager.process.stdout if has_process else None
            
            # Log state changes
            current_state = (has_process, has_stdout is not None)
            if current_state != last_process_state:
                if config.get("debug_mode"):
                    app_logger.debug(f"reader_thread state change: process={has_process}, stdout={has_stdout is not None}")
                last_process_state = current_state
            
            if server_manager.process and server_manager.process.stdout:
                line = server_manager.process.stdout.readline()
                if line:
                    if config.get("debug_mode"):
                        app_logger.debug(f"reader_thread: Read line: {line.strip()[:100]}...")  # Log first 100 chars
                    
                    # Parse for player join/leave events
                    join_match = re.search(r'(\w+)\[.+?\] logged in', line)
                    leave_match = re.search(r'(\w+) left the game', line)
                    
                    if join_match:
                        username = join_match.group(1)
                        server_manager.players[username] = time.time()
                        app_logger.info(f"Player joined: {username}")
                    elif leave_match:
                        username = leave_match.group(1)
                        if username in server_manager.players:
                            del server_manager.players[username]
                            app_logger.info(f"Player left: {username}")
                    
                    server_manager.log_history.append(line)
                    server_manager.publish_queue.put(line)
                else:
                    if config.get("debug_mode"): 
                        poll_result = server_manager.process.poll()
                        app_logger.debug(f"reader_thread: Empty line, poll()={poll_result}")
                    # Process ended or stream closed
                    if not server_manager.is_running():
                         time.sleep(1)
            else:
                # No process running
                time.sleep(1)
        except Exception as e:
             app_logger.error(f"Reader thread exception: {e}")
             if config.get("debug_mode"): app_logger.log(f"[ERROR] reader_thread exception: {e}")
             # Prevent thread crash on IO errors
             time.sleep(1)

server_manager = ServerManager()

# Start the reading thread
t = threading.Thread(target=reader_thread, args=(server_manager,), daemon=True)
t.start()
