@echo off
:: Verifica se já está rodando como admin
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Solicitando permissoes de administrador...
    powershell -Command "Start-Process '%~f0' -Verb RunAs"
    exit /b
)

cd /d "C:\SOFTWARE_ELETROLISADOR"
call "C:\SOFTWARE_ELETROLISADOR\venv\Scripts\activate"
python "C:\SOFTWARE_ELETROLISADOR\main.py"
pause