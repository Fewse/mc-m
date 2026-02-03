import threading
import time
import queue
import sys
import os

# Add project root to path
sys.path.append(os.getcwd())

from app.server_manager import server_manager, reader_thread
from app.logger import app_logger
from app.config import config

def test_diagnostics():
    print("=== Diagnostic Test ===")
    
    # 1. Check Config
    print(f"Debug Mode in Config: {config.get('debug_mode')}")
    
    # 2. Check Thread
    print(f"\nChecking Threads...")
    found_reader = False
    for t in threading.enumerate():
        print(f"  - Thread: {t.name} (Daemon: {t.daemon}, Alive: {t.is_alive()})")
        if t.name == "Thread-1" or "reader_thread" in str(t): # Name might vary
             found_reader = True
             
    # In server_manager.py it is just t = threading.Thread(...) so name is likely Thread-X
    # We can check if server_manager has the attribute 't' if I can access it locally,
    # but the module defines 't' at module level, not class level.
    # Let's inspect the module dict if possible or just rely on enumeration.
    
    # 3. Check Logger
    print(f"\nChecking Logger...")
    q = queue.Queue()
    app_logger.listeners.append(q)
    
    test_msg = "test_log_message"
    app_logger.log(test_msg)
    
    try:
        msg = q.get(timeout=1)
        print(f"  [PASS] Logger broadcast received: {msg.strip()}")
    except queue.Empty:
        print(f"  [FAIL] Logger broadcast NOT received")
        
    # 4. Check Queue Binding in Reader Thread
    # We can't easily inject into the running thread without mocking, 
    # but we can check if server_manager.publish_queue receives data if we simulate process output?
    # Hard to simulate process stdout on existing instance without potentially breaking it if it was running.
    
    print("\n=== End Diagnostics ===")

if __name__ == "__main__":
    test_diagnostics()
