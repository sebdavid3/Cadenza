@echo off
echo ==========================================================
echo          Iniciando Cadenza OMR en Modo Local
echo ==========================================================

call conda activate homr-proto

set "ROOT_DIR=%~dp0.."

echo [*] Levantando Backend FastAPI en http://localhost:8000 ...
start "Cadenza Backend" cmd /k "cd /d "%ROOT_DIR%\backend" && python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload"

echo [*] Levantando Frontend Vite en http://localhost:5173 ...
start "Cadenza Frontend" cmd /k "cd /d "%ROOT_DIR%\frontend" && npm run dev -- --host 0.0.0.0 --port 5173"

echo.
echo ==========================================================
echo  Backend:  http://localhost:8000/docs
echo  Frontend: http://localhost:5173
echo ==========================================================
