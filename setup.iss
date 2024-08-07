[Setup]
AppName=Ominis-OSINT
AppVersion=0.4.8
DefaultDirName={pf}\Ominis-OSINT
DefaultGroupName=Ominis-OSINT
OutputDir=.\Output
OutputBaseFilename=OminisInstaller
Compression=lzma
SolidCompression=yes

[Files]
Source: "install.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "omnis.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion

[Run]
Filename: "{app}\install.bat"; Parameters: ""; WorkingDir: "{app}"; Flags: runhidden
