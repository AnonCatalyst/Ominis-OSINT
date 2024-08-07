@echo off
setlocal

rem Set the installation directory
set "destination_dir=%ProgramFiles%\Ominis-OSINT"

rem Create the installation directory if it doesn't exist
if not exist "%destination_dir%" (
    mkdir "%destination_dir%"
)

rem Copy files to the installation directory
xcopy /E /I /Y . "%destination_dir%"

rem Install requirements from requirements.txt
python -m pip install --break-system-packages -r requirements.txt

rem Add the Ominis-OSINT directory to the system PATH
setx PATH "%PATH%;%destination_dir%"

echo Installation complete.
