from fastapi import Request, HTTPException
from time import time
from collections import defaultdict

# Simple in-memory rate limiter
# IP -> list of timestamps
failed_attempts = defaultdict(list)
LOCKOUT_TIME = 300 # 5 minutes
MAX_ATTEMPTS = 5
WINDOW = 60 # 1 minute to accumulate failures

def check_rate_limit(request: Request):
    client_ip = request.client.host
    now = time()
    
    # Cleanup old attempts
    failed_attempts[client_ip] = [t for t in failed_attempts[client_ip] if t > now - WINDOW]
    
    if len(failed_attempts[client_ip]) >= MAX_ATTEMPTS:
        # Check if last attempt was recent enough to still be locked out
        # Actually simplest is just: if count > max, lockout for Lockout Time from last failure
        last_fail = failed_attempts[client_ip][-1]
        if now - last_fail < LOCKOUT_TIME:
             raise HTTPException(status_code=429, detail="Too many failed login attempts. Try again later.")
        else:
             # Reset if lockout expired
             failed_attempts[client_ip] = []

def record_failed_attempt(request: Request):
    client_ip = request.client.host
    failed_attempts[client_ip].append(time())
