@echo off
cd /d "%~dp0"

set "PY=%~dp0.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo.
  echo No se encontro Python en .venv
  echo Ejecute primero: instalar.bat
  echo.
  pause
  exit /b 1
)

echo.
echo ========================================
echo   Gastos de choferes - iniciando...
echo ========================================
echo.
echo Abra en el navegador: http://localhost:5000
echo.
echo Chofer: DNI + telefono
echo Admin:  http://localhost:5000/admin/login  (clave por defecto: admin123)
echo Master: http://localhost:5000/master/login (clave por defecto: master123)
echo.
echo Presione Ctrl+C para detener.
echo.

"%PY%" app.py
pause
