#auth.py
import os
from datetime import datetime, timedelta
from jose import jwt, JWTError
from passlib.context import CryptContext
from fastapi import Request, HTTPException, Depends, status
from .database import get_db
from .models import User

SECRET_KEY = os.getenv("SECRET_KEY", "super-secret-fcss-key")
ALGORITHM = os.getenv("ALGORITHM","HS256")
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def hash_password(password: str):
    if not password: password = "default_secure_pass"
    encoded_pw = password.encode('utf-8')
    if len(encoded_pw) > 72: password = password[:72] # Bcrypt limit check
    return pwd_context.hash(password)

def verify_password(plain, hashed): return pwd_context.verify(plain, hashed)
def create_access_token(username: str): return jwt.encode({"sub": username, "exp": datetime.utcnow() + timedelta(days=30)}, SECRET_KEY, algorithm=ALGORITHM)

#def get_current_user(token: str, db: Session):
async def get_current_user(request: Request, db = Depends(get_db)):
    token = request.cookies.get("access_token")
    if not token:
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "): token = auth_header.split(" ")[1]
    if not token: raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username: raise HTTPException(status_code=401, detail="Invalid token payload")
        user = db.query(User).filter(User.username == username).first()
        if not user: raise HTTPException(status_code=401, detail="User not found")
        return user # Now guaranteed to be a User object
    except JWTError:
        raise HTTPException(status_code=401, detail="Session expired")
