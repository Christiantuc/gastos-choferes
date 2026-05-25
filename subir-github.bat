@echo off
cd /d "%~dp0"

if exist "C:\Program Files\Git\cmd\git.exe" set "PATH=C:\Program Files\Git\cmd;%PATH%"
if exist "C:\Program Files\GitHub CLI\gh.exe" set "PATH=C:\Program Files\GitHub CLI;%PATH%"

echo Subiendo Gastos a GitHub (Christiantuc/gastos-choferes)...
echo.

where git >nul 2>&1 || (echo Instale Git. & pause & exit /b 1)

if not exist ".git" (
  git init
  git branch -M main
)

git add .
git diff --cached --quiet || git commit -m "Actualizacion app gastos"

where gh >nul 2>&1
if %errorlevel% equ 0 (
  gh auth status >nul 2>&1
  if %errorlevel% equ 0 (
    gh repo create gastos-choferes --public --source=. --remote=origin --push 2>nul
    if %errorlevel% neq 0 git push -u origin main
    echo.
    echo Listo: https://github.com/Christiantuc/gastos-choferes
    pause
    exit /b 0
  )
)

echo Ejecute primero: gh auth login
echo Luego vuelva a ejecutar este archivo.
pause
