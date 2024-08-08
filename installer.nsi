OutFile "OminisInstaller.exe"
InstallDir "$PROGRAMFILES\Ominis-OSINT"
RequestExecutionLevel user

Section "MainSection" SEC01
  SetOutPath "$INSTDIR"
  File "install.bat"
  File "ominis.exe"
  File "requirements.txt"
SectionEnd

Section "PostInstall"
  ExecWait '"$INSTDIR\install.bat"'
SectionEnd

