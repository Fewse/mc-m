import hashlib
import secrets
from fastapi import HTTPException, status, Depends
from fastapi.security import OAuth2PasswordBearer
from app.config import config

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def verify_password(plain_password: str, hashed_password: str) -> bool:
    return hash_password(plain_password) == hashed_password

def setup_initial_password():
    """Checks if password is set, if not, generates one."""
    current_hash = config.get("admin_password_hash")
    if not current_hash:
        # Generate a random password
        temp_pass = secrets.token_urlsafe(12)
        print(f"\n[IMPORTANT] No admin password set. Generated password: {temp_pass}\n")
        config.set("admin_password_hash", hash_password(temp_pass))

setup_initial_password() # Run on module load to ensure secure setup


# Actual JWT implementation
from datetime import datetime, timedelta
from jose import JWTError, jwt

ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 # 1 day

def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, config.get("secret_key"), algorithm=ALGORITHM)
    return encoded_jwt

async def get_current_user(token: str = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, config.get("secret_key"), algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception
    return username

async def get_current_active_user(current_user: str = Depends(get_current_user)):
    return current_user

def verify_token_str(token: str):
    try:
        payload = jwt.decode(token, config.get("secret_key"), algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        return username
    except JWTError:
        return None
