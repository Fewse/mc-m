import sys
import queue
from datetime import datetime

class AppLogger:
    def __init__(self):
        self.terminal = sys.stdout
        self.log_queue = queue.Queue()
        self.listeners = []
        
        # Monkey patch stdout/stderr to capture everything
        sys.stdout = self
        sys.stderr = self

    def write(self, message):
        self.terminal.write(message)
        if message.strip(): # Don't send empty newlines alone
            timestamp = datetime.now().strftime("%H:%M:%S")
            formatted = f"[{timestamp}] {message.strip()}"
            self.broadcast(formatted)

    def flush(self):
        self.terminal.flush()

    def log(self, message):
        self.write(message + "\n")

    def broadcast(self, message):
        # Using list copy to be safe
        for q in list(self.listeners):
             try:
                 q.put_nowait(message)
             except queue.Full:
                 pass

app_logger = AppLogger()
