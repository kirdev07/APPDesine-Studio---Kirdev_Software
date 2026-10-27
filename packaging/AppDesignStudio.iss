; Установщик App Design Studio (Inno Setup 6). Сборка: ISCC.exe /DAppVersion=1.0.0 packaging\AppDesignStudio.iss
#ifndef AppVersion
  #define AppVersion "1.0.0"
#endif

[Setup]
AppId={{6C7E2B1A-4E0D-4B6F-9F3C-0AD5100000A1}
AppName=App Design Studio
AppVersion={#AppVersion}
AppPublisher=Kirdev Software
AppCopyright=© 2026 Kirdev Software. Все права защищены.
DefaultDirName={autopf}\App Design Studio
DefaultGroupName=App Design Studio
OutputDir=..\dist
OutputBaseFilename=AppDesignStudio-{#AppVersion}-setup
SetupIconFile=app.ico
UninstallDisplayIcon={app}\AppDesignStudio.exe
LicenseFile=..\LICENSE
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequiredOverridesAllowed=dialog
MinVersion=10.0

[Languages]
Name: "ru"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; Flags: unchecked

[Files]
Source: "..\dist\AppDesignStudio\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\App Design Studio"; Filename: "{app}\AppDesignStudio.exe"
Name: "{autodesktop}\App Design Studio"; Filename: "{app}\AppDesignStudio.exe"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\.adsproj"; ValueType: string; ValueData: "AppDesignStudio.Project"; Flags: uninsdeletevalue
Root: HKA; Subkey: "Software\Classes\AppDesignStudio.Project"; ValueType: string; ValueData: "Проект App Design Studio"; Flags: uninsdeletekey
Root: HKA; Subkey: "Software\Classes\AppDesignStudio.Project\shell\open\command"; ValueType: string; ValueData: """{app}\AppDesignStudio.exe"" ""%1"""

[Run]
Filename: "{app}\AppDesignStudio.exe"; Description: "{cm:LaunchProgram,App Design Studio}"; Flags: nowait postinstall skipifsilent
