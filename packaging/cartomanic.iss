; Inno Setup script for Cartomanic BR.
;
; Compiles dist/CartomanicBR/ (the PyInstaller --onedir output, already
; pruned -- see packaging/README.md) into a single compressed installer.
; LZMA2/ultra64 + solid compression is the actual "best compression" move
; for this app: the heavy dependencies (pyarrow/GDAL/duckdb) are already
; optimized native binaries that UPX barely touches, so compression
; belongs in the *distributable*, not the installed files themselves.
;
; Build (from the repo root):
;   "C:\Users\<you>\AppData\Local\Programs\Inno Setup 6\ISCC.exe" packaging\cartomanic.iss
;
; Requires dist/CartomanicBR/ to already exist -- run the PyInstaller build
; first (see packaging/README.md).
;
; AppId is a fixed GUID: Inno Setup uses it to recognize "this is the same
; app, a different version" across installs/upgrades. Generated once;
; never change it for this app, even across major versions.
#define MyAppName "Cartomanic BR"
#define MyAppVersion "1.1.0"
#define MyAppPublisher "Emanuel Barroso"
#define MyAppExeName "CartomanicBR.exe"

[Setup]
; Written as a raw literal (not via #define + {#...}) on purpose: mixing
; the preprocessor's {#Name} token with the compiler's own {{ brace-escape
; on the same line is a classic Inno footgun -- the preprocessor consumes
; one of the two opening braces as part of its own token, leaving the
; compiler with an unbalanced "{{" it can't resolve. A raw "{{GUID}" has
; no "#" in it, so the preprocessor never touches this line at all.
AppId={{7F19EFAC-3B86-4101-8E12-4D3309F8A93C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultGroupName={#MyAppName}
UninstallDisplayIcon={app}\{#MyAppExeName}
; Per-user install, no admin prompt -- a map-building hobby app has no
; business asking for elevation.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\CartomanicBR
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\installer_output
OutputBaseFilename=CartomanicBR-Setup-{#MyAppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
DisableProgramGroupPage=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
; The whole pruned --onedir output, recursively, preserving structure.
Source: "..\dist\CartomanicBR\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent
