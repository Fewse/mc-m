from fastapi import FastAPI, Depends, WebSocket, WebSocketDisconnect, HTTPException, Request, Query, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.security import OAuth2PasswordRequestForm
from app.auth import oauth2_scheme, verify_password, create_access_token, get_current_active_user, config, hash_password, verify_token_str
from app.server_manager import server_manager
from app.rate_limiter import check_rate_limit, record_failed_attempt
from app.backup_manager import backup_manager
from pydantic import BaseModel
import asyncio
import os
from app.logger import app_logger

app_logger.info("="*80)
app_logger.info("MINECRAFT SERVER MANAGER APPLICATION STARTING")
app_logger.info("="*80)

app = FastAPI()

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

class Token(BaseModel):
    access_token: str
    token_type: str

class Settings(BaseModel):
    server_name: str
    jar_path: str
    java_path: str
    ram_min: str
    ram_max: str
    server_dir: str
    backup_path: str
    debug_mode: bool = False

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class Command(BaseModel):
    command: str

@app.post("/token", response_model=Token)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    client_ip = request.client.host
    app_logger.info(f"Login attempt from {client_ip} for user: {form_data.username}")
    check_rate_limit(request)
    stored_hash = config.get("admin_password_hash")
    if not verify_password(form_data.password, stored_hash):
        record_failed_attempt(request)
        app_logger.warning(f"Failed login attempt from {client_ip} for user: {form_data.username}")
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    access_token = create_access_token(data={"sub": form_data.username})
    app_logger.info(f"✓ Successful login from {client_ip} for user: {form_data.username}")
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/", response_class=HTMLResponse)
async def get_root():
    return FileResponse("app/static/index.html")

@app.get("/api/stats")
async def get_stats(current_user: str = Depends(get_current_active_user)):
    app_logger.debug(f"Stats requested by user: {current_user}")
    return server_manager.get_stats()

@app.post("/api/start")
async def start_server(current_user: str = Depends(get_current_active_user)):
    app_logger.info(f"Server start requested by user: {current_user}")
    return server_manager.start_server()

@app.post("/api/stop")
async def stop_server(current_user: str = Depends(get_current_active_user)):
    app_logger.info(f"Server stop requested by user: {current_user}")
    return await server_manager.stop_server()

@app.post("/api/command")
async def send_command(cmd: Command, current_user: str = Depends(get_current_active_user)):
    app_logger.info(f"Command sent by {current_user}: {cmd.command}")
    server_manager.send_command(cmd.command)
    return {"status": "sent"}

@app.get("/api/settings")
async def get_settings(current_user: str = Depends(get_current_active_user)):
    return config.config

@app.post("/api/settings")
async def update_settings(settings: Settings, current_user: str = Depends(get_current_active_user)):
    app_logger.info(f"Settings update requested by user: {current_user}")
    app_logger.info(f"  Server name: {settings.server_name}")
    app_logger.info(f"  JAR path: {settings.jar_path}")
    app_logger.info(f"  Server dir: {settings.server_dir}")
    app_logger.info(f"  RAM: {settings.ram_min} - {settings.ram_max}")
    app_logger.info(f"  Debug mode: {settings.debug_mode}")
    
    config.set("server_name", settings.server_name)
    config.set("jar_path", settings.jar_path)
    config.set("java_path", settings.java_path)
    config.set("ram_min", settings.ram_min)
    config.set("ram_max", settings.ram_max)
    config.set("server_dir", settings.server_dir)
    config.set("backup_path", settings.backup_path)
    config.set("debug_mode", settings.debug_mode)
    app_logger.info("✓ Settings updated successfully")
    return {"status": "updated"}

@app.post("/api/change-password")
async def change_password(data: PasswordChange, current_user: str = Depends(get_current_active_user)):
    app_logger.info(f"Password change requested by user: {current_user}")
    stored_hash = config.get("admin_password_hash")
    if not verify_password(data.current_password, stored_hash):
        app_logger.warning(f"Password change failed: Incorrect current password")
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    config.set("admin_password_hash", hash_password(data.new_password))
    app_logger.info(f"✓ Password changed successfully by user: {current_user}")
    return {"status": "success", "message": "Password changed"}

# File Editor
@app.get("/api/file")
async def get_file_content(path: str, current_user: str = Depends(get_current_active_user)):
    app_logger.info(f"File read requested by {current_user}: {path}")
    target = os.path.realpath(os.path.join(config.get("server_dir"), path))
    server_root = os.path.realpath(config.get("server_dir"))
    
    if not target.startswith(server_root):
        app_logger.warning(f"File access denied: {path} (outside server root)")
        raise HTTPException(status_code=403, detail="Access denied")
    
    if os.path.exists(target) and os.path.isfile(target):
        try:
            with open(target, 'r') as f:
                return {"content": f.read()}
        except Exception:
             app_logger.error(f"Error reading file: {path}")
             return {"content": "Error reading file."}
    return {"content": ""}

@app.post("/api/file")
async def save_file_content(path: str, content: Command, current_user: str = Depends(get_current_active_user)): 
    app_logger.info(f"File save requested by {current_user}: {path}")
    target = os.path.realpath(os.path.join(config.get("server_dir"), path))
    server_root = os.path.realpath(config.get("server_dir"))
    
    if not target.startswith(server_root):
        app_logger.warning(f"File save denied: {path} (outside server root)")
        raise HTTPException(status_code=403, detail="Access denied")
    
    with open(target, 'w') as f:
        f.write(content.command)
    app_logger.info(f"✓ File saved: {path}")
    return {"status": "saved"}

# Backups
@app.get("/api/backups")
async def list_backups(current_user: str = Depends(get_current_active_user)):
    return backup_manager.list_backups()

@app.get("/api/backups/usage")
async def get_backup_usage(current_user: str = Depends(get_current_active_user)):
    return backup_manager.get_disk_usage()

@app.get("/api/backups/status")
async def get_backup_status(current_user: str = Depends(get_current_active_user)):
    return backup_manager.get_status()

@app.post("/api/backups/cancel")
async def cancel_backup_task(current_user: str = Depends(get_current_active_user)):
    return backup_manager.cancel_backup()

@app.post("/api/backups")
async def create_backup(type: str = "world", current_user: str = Depends(get_current_active_user)):
    app_logger.info(f"Backup creation requested by {current_user}: type={type}")
    return await backup_manager.create_backup(type, "world")

@app.delete("/api/backups/{filename}")
async def delete_backup(filename: str, current_user: str = Depends(get_current_active_user)):
    app_logger.info(f"Backup deletion requested by {current_user}: {filename}")
    return backup_manager.delete_backup(filename)

# Logs
@app.get("/api/logs")
async def get_logs(lines: int = 200, current_user: str = Depends(get_current_active_user)):
    """Reads the last N lines of logs/latest.log"""
    log_path = os.path.join(config.get("server_dir"), "logs", "latest.log")
    if not os.path.exists(log_path):
        return {"content": "No log file found."}
    
    try:
        with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
            # Efficient tail implementation is needed for huge logs, 
            # but for this scale reading all is okay-ish or seek.
            # Let's do a simple readlines and tail.
            all_lines = f.readlines()
            return {"content": "".join(all_lines[-lines:])}
    except Exception as e:
        return {"content": f"Error reading log: {str(e)}"}


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcast_logs())

async def broadcast_logs():
    """Background task to broadcast logs to all connected clients."""
    while True:
        try:
            # Blocking get from queue, run in thread
            line = await asyncio.to_thread(server_manager.publish_queue.get)
            
            # Broadcast to all client queues
            # We iterate a copy to handle dynamic addition/removal safely, 
            # though usually list operations are atomic enough for this in GIL.
            for q in list(server_manager.listeners):
                try:
                    q.put_nowait(line)
                except asyncio.QueueFull:
                    pass # Slow client, drop message?
        except Exception as e:
            print(f"Broadcast error: {e}")
            await asyncio.sleep(1)



@app.websocket("/ws/debug")
async def websocket_debug(websocket: WebSocket, token: str = Query(None)):
    if not config.get("debug_mode"):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    if not token or not verify_token_str(token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    app_logger.info("Debug WebSocket client connected")
    
    client_queue = asyncio.Queue(maxsize=500)
    app_logger.listeners.append(client_queue)
    
    try:
        while True:
            # Simple stream of app logs
            line = await client_queue.get()
            await websocket.send_text(line)
            
    except WebSocketDisconnect:
        app_logger.info("Debug WebSocket client disconnected")
        if client_queue in app_logger.listeners:
            app_logger.listeners.remove(client_queue)
    except Exception as e:
        app_logger.error(f"Debug WebSocket error: {e}")
        if client_queue in app_logger.listeners:
            app_logger.listeners.remove(client_queue)

# WebSocket for Console
@app.websocket("/ws/console")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
# ... existing code ...
    if not token or not verify_token_str(token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    app_logger.info("Console WebSocket client connected")
    
    # Create a personal queue for this client
    client_queue = asyncio.Queue(maxsize=500)
    server_manager.listeners.append(client_queue)
    if config.get("debug_mode"): print(f"[TRACE] WS: Console Client connected. Total clients: {len(server_manager.listeners)}")
    
    try:
        # Send history first
        for line in list(server_manager.log_history):
             await websocket.send_text(line)

        while True:
            line = await client_queue.get()
            await websocket.send_text(line)
            
    except WebSocketDisconnect:
        app_logger.info("Console WebSocket client disconnected")
        if config.get("debug_mode"): print(f"[TRACE] WS: Console Client disconnected.")
        if client_queue in server_manager.listeners:
            server_manager.listeners.remove(client_queue)
    except Exception as e:
        app_logger.error(f"Console WebSocket error: {e}")
        if config.get("debug_mode"): print(f"[TRACE] WS: Error {e}")
        if client_queue in server_manager.listeners:
            server_manager.listeners.remove(client_queue)
