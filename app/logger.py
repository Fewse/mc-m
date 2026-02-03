import sys
import queue
import os
from datetime import datetime
from pathlib import Path

class AppLogger:
    def __init__(self):
        self.terminal = sys.stdout
        self.log_queue = queue.Queue()
        self.listeners = []
        self.log_file = None
        self.log_file_path = None
        
        # Create logs directory
        self._setup_log_file()
        
        # Monkey patch stdout/stderr to capture everything
        sys.stdout = self
        sys.stderr = self

    def _setup_log_file(self):
        """Create logs directory and open a new log file with timestamp"""
        # Get the project root (parent of app/ directory)
        project_root = Path(__file__).parent.parent
        logs_dir = project_root / "logs"
        
        # Create logs directory if it doesn't exist
        logs_dir.mkdir(exist_ok=True)
        
        # Generate timestamped filename
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        self.log_file_path = logs_dir / f"app_{timestamp}.log"
        
        # Open log file
        try:
            self.log_file = open(self.log_file_path, 'w', encoding='utf-8', buffering=1)
            self._write_to_file(f"=== Application Log Started at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            self._write_to_file(f"Log file: {self.log_file_path}\n")
            self._write_to_file("=" * 80 + "\n")
        except Exception as e:
            print(f"ERROR: Failed to create log file: {e}", file=sys.__stdout__)

    def _write_to_file(self, message):
        """Write message to log file"""
        if self.log_file:
            try:
                self.log_file.write(message)
                self.log_file.flush()
            except Exception as e:
                print(f"ERROR: Failed to write to log file: {e}", file=sys.__stdout__)

    def write(self, message):
        """Capture all stdout/stderr and write to console, file, and WebSocket"""
        self.terminal.write(message)
        
        if message.strip():
            # Full timestamp for file
            full_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            self._write_to_file(f"[{full_timestamp}] {message.strip()}\n")
            
            # Short timestamp for WebSocket
            short_timestamp = datetime.now().strftime("%H:%M:%S")
            formatted = f"[{short_timestamp}] {message.strip()}"
            self.broadcast(formatted)

    def flush(self):
        self.terminal.flush()
        if self.log_file:
            self.log_file.flush()

    def log(self, message, level="INFO"):
        """Log a message with a specific level"""
        full_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        formatted_message = f"[{full_timestamp}] [{level}] {message}"
        self.terminal.write(formatted_message + "\n")
        self._write_to_file(formatted_message + "\n")
        
        # Also broadcast to WebSocket with short timestamp
        short_timestamp = datetime.now().strftime("%H:%M:%S")
        ws_message = f"[{short_timestamp}] [{level}] {message}"
        self.broadcast(ws_message)

    def debug(self, message):
        """Log a debug message"""
        self.log(message, "DEBUG")
    
    def info(self, message):
        """Log an info message"""
        self.log(message, "INFO")
    
    def warning(self, message):
        """Log a warning message"""
        self.log(message, "WARN")
    
    def error(self, message):
        """Log an error message"""
        self.log(message, "ERROR")

    def broadcast(self, message):
        """Broadcast to WebSocket listeners"""
        for q in list(self.listeners):
             try:
                 q.put_nowait(message)
             except queue.Full:
                 pass

    def close(self):
        """Close the log file"""
        if self.log_file:
            self._write_to_file(f"\n=== Application Log Ended at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} ===\n")
            self.log_file.close()
            self.log_file = None

app_logger = AppLogger()
