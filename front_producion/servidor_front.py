import asyncio
import socket
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "dist" / "comat" / "browser"
CERTS_DIR = BASE_DIR / "certs"

HOST = "0.0.0.0"
PORT = 9001

if hasattr(asyncio, "WindowsSelectorEventLoopPolicy"):
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# -------------------------
# 🔥 Obtener IP real
# -------------------------
def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
    except:
        ip = "127.0.0.1"
    finally:
        s.close()
    return ip

# -------------------------
# 🔐 Certificado autofirmado
# -------------------------
def generate_self_signed_cert():
    cert_file = CERTS_DIR / "cert.pem"
    key_file = CERTS_DIR / "key.pem"

    if cert_file.exists() and key_file.exists():
        return str(cert_file), str(key_file)

    CERTS_DIR.mkdir(exist_ok=True)

    try:
        from cryptography import x509
        from cryptography.x509.oid import NameOID
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.hazmat.primitives import serialization
        import datetime

        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend()
        )

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COUNTRY_NAME, u"CO"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, u"COMATE"),
            x509.NameAttribute(NameOID.COMMON_NAME, u"localhost"),
        ])

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(private_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.utcnow())
            .not_valid_after(
                datetime.datetime.utcnow() + datetime.timedelta(days=365)
            )
            .add_extension(
                x509.SubjectAlternativeName([
                    x509.DNSName(u"localhost"),
                ]),
                critical=False,
            )
            .sign(private_key, hashes.SHA256(), default_backend())
        )

        with open(cert_file, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        with open(key_file, "wb") as f:
            f.write(
                private_key.private_bytes(
                    encoding=serialization.Encoding.PEM,
                    format=serialization.PrivateFormat.TraditionalOpenSSL,
                    encryption_algorithm=serialization.NoEncryption(),
                )
            )

        return str(cert_file), str(key_file)

    except ImportError:
        return None, None

# -------------------------
# 🚀 FastAPI
# -------------------------
app = FastAPI()

# 🔥 Compresión
app.add_middleware(GZipMiddleware, minimum_size=1000)

# 🔥 CORS (puedes ajustar luego)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------
# ⚡ Static con cache
# -------------------------
class CacheStaticFiles(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)

        # Cache agresivo para archivos estáticos
        if path.endswith((".js", ".css", ".png", ".jpg", ".jpeg", ".svg", ".ico")):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"

        # HTML no cache (Angular index)
        elif path.endswith(".html"):
            response.headers["Cache-Control"] = "no-cache"

        return response

app.mount("/assets", CacheStaticFiles(directory=STATIC_DIR), name="static")

# -------------------------
# 🧠 Angular SPA fallback
# -------------------------
@app.get("/{full_path:path}")
async def serve_spa(request: Request, full_path: str):
    file_path = STATIC_DIR / full_path

    if file_path.exists() and file_path.is_file():
        return FileResponse(file_path)

    return FileResponse(STATIC_DIR / "index.html")

# -------------------------
# 🚀 Run
# -------------------------
if __name__ == "__main__":
    import uvicorn

    cert_file, key_file = generate_self_signed_cert()
    local_ip = get_local_ip()

    print("\n" + "=" * 60)
    print("🚀 Servidor listo")
    print(f"Local: https://localhost:{PORT}")
    print(f"Red:   https://{local_ip}:{PORT}")
    print("⚠️ Certificado autofirmado (solo red interna)")
    print("=" * 60 + "\n")

    uvicorn.run(
        app,
        host=HOST,
        port=PORT,
        ssl_certfile=cert_file,
        ssl_keyfile=key_file
    )