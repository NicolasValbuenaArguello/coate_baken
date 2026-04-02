from jose import jwt, JWTError
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv

load_dotenv()

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
TOKEN_MINUTES = 120


# =========================
# CREAR TOKEN
# =========================

def crear_token(data: dict):

    to_encode = data.copy()

    expire = datetime.utcnow() + timedelta(minutes=TOKEN_MINUTES)

    to_encode.update({"exp": expire})

    token = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

    return token


# =========================
# VALIDAR TOKEN
# =========================

def validar_token(token: str):

    try:

        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])

        return payload

    except JWTError:

        return None