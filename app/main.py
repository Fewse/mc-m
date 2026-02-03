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

class PasswordChange(BaseModel):
    current_password: str
    new_password: str

class Command(BaseModel):
    command: str

@app.post("/token", response_model=Token)
async def login_for_access_token(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    check_rate_limit(request)
    stored_hash = config.get("admin_password_hash")
    if not verify_password(form_data.password, stored_hash):
        record_failed_attempt(request)
        raise HTTPException(status_code=400, detail="Incorrect password")
    
    access_token = create_access_token(data={"sub": form_data.username})
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/", response_class=HTMLResponse)
async def get_root():
    return FileResponse("app/static/index.html")

@app.get("/api/stats")
async def get_stats(current_user: str = Depends(get_current_active_user)):
    return server_manager.get_stats()

@app.post("/api/start")
async def start_server(current_user: str = Depends(get_current_active_user)):
    return server_manager.start_server()

@app.post("/api/stop")
async def stop_server(current_user: str = Depends(get_current_active_user)):
    return server_manager.stop_server()

@app.post("/api/command")
async def send_command(cmd: Command, current_user: str = Depends(get_current_active_user)):
    server_manager.send_command(cmd.command)
    return {"status": "sent"}

@app.get("/api/settings")
async def get_settings(current_user: str = Depends(get_current_active_user)):
    return config.config

@app.post("/api/settings")
async def update_settings(settings: Settings, current_user: str = Depends(get_current_active_user)):
    config.set("server_name", settings.server_name)
    config.set("jar_path", settings.jar_path)
    config.set("java_path", settings.java_path)
    config.set("ram_min", settings.ram_min)
    config.set("ram_max", settings.ram_max)
    config.set("server_dir", settings.server_dir)
    config.set("backup_path", settings.backup_path)
    return {"status": "updated"}

@app.post("/api/change-password")
async def change_password(data: PasswordChange, current_user: str = Depends(get_current_active_user)):
    stored_hash = config.get("admin_password_hash")
    if not verify_password(data.current_password, stored_hash):
        raise HTTPException(status_code=400, detail="Incorrect current password")
    
    config.set("admin_password_hash", hash_password(data.new_password))
    return {"status": "success", "message": "Password changed"}

# File Editor
@app.get("/api/file")
async def get_file_content(path: str, current_user: str = Depends(get_current_active_user)):
    target = os.path.join(config.get("server_dir"), path)
    if not os.path.abspath(target).startswith(os.path.abspath(config.get("server_dir"))):
        raise HTTPException(status_code=403, detail="Access denied")
    
    if os.path.exists(target) and os.path.isfile(target):
        try:
            with open(target, 'r') as f:
                return {"content": f.read()}
        except Exception:
             return {"content": "Error reading file."}
    return {"content": ""}

@app.post("/api/file")
async def save_file_content(path: str, content: Command, current_user: str = Depends(get_current_active_user)): 
    target = os.path.join(config.get("server_dir"), path)
    if not os.path.abspath(target).startswith(os.path.abspath(config.get("server_dir"))):
        raise HTTPException(status_code=403, detail="Access denied")
    
    with open(target, 'w') as f:
        f.write(content.command)
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
    return await backup_manager.create_backup(type, "world")

@app.delete("/api/backups/{filename}")
async def delete_backup(filename: str, current_user: str = Depends(get_current_active_user)):
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


# WebSocket for Console
@app.websocket("/ws/console")
async def websocket_endpoint(websocket: WebSocket, token: str = Query(None)):
    if not token or not verify_token_str(token):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    await websocket.accept()
    try:
        while True:
            # Poll queue
            while not server_manager.console_queue.empty():
                line = server_manager.console_queue.get()
                await websocket.send_text(line)
            await asyncio.sleep(0.5)
    except WebSocketDisconnect:
        pass
