from fastapi import Header, HTTPException
from auth.jwt_manager import validar_token

def verificar_token(authorization: str = Header(None)):

    #print("HEADER AUTH:", authorization)   # ← DEBUG

    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="No se envió Authorization header"
        )

    token = authorization.replace("Bearer ", "")

    payload = validar_token(token)

    if not payload:
        raise HTTPException(
            status_code=401,
            detail="Token inválido"
        )

    return payload