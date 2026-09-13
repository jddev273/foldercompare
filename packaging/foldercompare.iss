#ifndef MyAppVersion
  #define MyAppVersion "0.1.0"
#endif
#define MyAppName "FolderCompare"
#define MyAppExeName "FolderCompare.exe"

[Setup]
AppId={{C93FBB2B-0C71-4C8C-9A70-E43E6C4CD78B}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=FolderCompare contributors
DefaultDirName={autopf}\FolderCompare
DefaultGroupName=FolderCompare
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
OutputDir=..\release
OutputBaseFilename=FolderCompare-setup
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest

[Files]
Source: "..\dist\FolderCompare.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\FolderCompare"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch FolderCompare"; Flags: nowait postinstall skipifsilent
