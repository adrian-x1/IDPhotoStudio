; Inno Setup script for IDPhotoStudio.
; Version is injected by CI: ISCC.exe /DAppVersion=1.0.0 installer\windows.iss
#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

#define AppName "IDPhotoStudio"
#define AppExeName "idphoto.exe"

[Setup]
AppId={{8F3A6C21-4E7B-4D59-9A2C-6B1E5D0F7A34}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=adrian-x1
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename={#AppName}-{#AppVersion}-Windows-x64-Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Per-machine install needs elevation; the bundle is far too large for {userpf}.
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExeName}
; The icon is optional so the installer still compiles before one is added.
#if FileExists(AddBackslash(SourcePath) + "..\assets\icon.ico")
SetupIconFile=..\assets\icon.ico
#endif

[Languages]
; Inno Setup only bundles Default.isl (English); ChineseSimplified.isl is a
; third-party file and is not present on the CI runner.
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional tasks:"

[Files]
Source: "..\dist\idphoto\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
