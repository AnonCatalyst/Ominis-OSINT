; Inno Setup script for the Ominis Investigation Workstation.
;
; Build from the repository root after PyInstaller has produced
; dist\OminisWorkstation.exe:
;
;     "C:\Users\<you>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" workstation.iss
;
; The installer is per-user, unsigned, and adds Desktop and Start menu
; shortcuts. It never bundles the StyxNet key or any case report.

#define MyAppName "Ominis Investigation Workstation"
#define MyAppVersion "1.0.6"
#define MyAppPublisher "WinterGate Intelligence Collective"
#define MyAppURL "https://wintergate.org"
#define MyAppExeName "OminisWorkstation.exe"

[Setup]
AppId={{B535CB39-1EDF-4E8C-B86C-2AD06C80E1EC}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL=https://github.com/AnonCatalyst/Ominis-OSINT/issues
AppUpdatesURL=https://github.com/AnonCatalyst/Ominis-OSINT/releases
AppComments=Native Qt desktop application for the Ominis engine. Bundled engine 1.2.6.
DefaultDirName={autopf}\Ominis Workstation
DefaultGroupName=Ominis Workstation
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
LicenseFile=LICENSE
OutputDir=dist
OutputBaseFilename=Ominis-Workstation-1.0.6-win64-setup
SetupIconFile=ominis_workstation\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no
ShowLanguageDialog=no
VersionInfoVersion=1.0.6.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription={#MyAppName} Setup
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
VersionInfoCopyright=MIT licensed. Maintained by AnonCatalyst with the WinterGate Intelligence Collective.

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: checkedonce

[Files]
Source: "dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "docs\workstation\README.md"; DestDir: "{app}"; DestName: "README.md"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "TRADEMARKS.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "CODE_SIGNING.md"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\Ominis Investigation Workstation"; Filename: "{app}\{#MyAppExeName}"; Comment: "Search, username checks, and StyxNet in one desk"
Name: "{autodesktop}\Ominis Investigation Workstation"; Filename: "{app}\{#MyAppExeName}"; Comment: "Search, username checks, and StyxNet in one desk"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
