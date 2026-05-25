@echo off
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel% equ 0 (
  set "PYBOOT=py -3.12"
) else (
  set "PYBOOT=python"
)

echo Instalando dependencias de Gastos...
if exist ".venv" rmdir /s /q ".venv"
%PYBOOT% -m venv .venv
if %errorlevel% neq 0 (
  echo Instale Python 3.12 desde https://www.python.org/downloads/
  pause
  exit /b 1
)

call .venv\Scripts\pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo Error al instalar.
  pause
  exit /b 1
)

echo.
echo Listo. Ahora ejecute iniciar.bat
pause
