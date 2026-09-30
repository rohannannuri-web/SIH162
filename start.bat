@echo off
echo ========================================================
echo        Starting HELIOS-X Intelligence System
echo ========================================================
echo.

echo [1/3] Starting Database (PostGIS via Docker)...
docker-compose up -d
echo.

echo [2/3] Starting Backend API...
start "HELIOS-X Backend API" cmd /k "cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
echo Backend starting in a new window...
echo.

echo [3/3] Starting Frontend Dashboard...
start "HELIOS-X Frontend" cmd /k "cd frontend && npm run dev"
echo Frontend starting in a new window...
echo.

echo ========================================================
echo System is launching! 
echo.
echo - The backend will run on http://127.0.0.1:8000
echo - The frontend dashboard will open at http://localhost:5173
echo.
echo Note: Keep the two new black terminal windows open.
echo       To stop the system, just close those windows.
echo ========================================================
pause
