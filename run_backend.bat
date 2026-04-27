@echo off
echo 🚀 Iniciando servidores...

start cmd /k python -m uvicorn login.main:app --reload --host 0.0.0.0 --port 8000
start cmd /k python -m uvicorn usuarios.usuarios:app --reload --host 0.0.0.0 --port 8001
start cmd /k python -m uvicorn personal.personal:app --reload --host 0.0.0.0 --port 8002
start cmd /k python -m uvicorn areas_subareas.areas:app --reload --host 0.0.0.0 --port 8003
start cmd /k python -m uvicorn carpetas.carpetas:app --reload --host 0.0.0.0 --port 8004
start cmd /k python -m uvicorn  proyectos.proyectos:app --reload --host 0.0.0.0 --port 8005
start cmd /k python .\front_producion\servidor_front.py
start cmd /k python .\servidor_archivos.py


echo ✅ Todos los servidores iniciados
pause