@echo off
setlocal
cd /d "%~dp0"

python -m venv .venv
if errorlevel 1 goto :error
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 goto :error

echo.
echo Installed. Run: .venv\Scripts\python.exe ominis.py -q "example query"
exit /b 0

:error
echo Installation failed.
exit /b 1
