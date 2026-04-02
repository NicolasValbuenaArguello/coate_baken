@echo off
echo 🚀 Iniciando servidores...

start cmd /k python -m uvicorn login.main:app --reload --port 8000
start cmd /k python -m uvicorn usuarios.usuarios:app --reload --port 8001
start cmd /k python -m uvicorn personal.personal:app --reload --port 8002
start cmd /k python -m uvicorn areas_subareas.areas:app --reload --port 8003
start cmd /k python servidor_archivos.py

echo ✅ Todos los servidores iniciados
pause