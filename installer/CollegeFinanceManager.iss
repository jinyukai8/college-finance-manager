#define MyAppName "学院组织资金管理助手"
#define MyAppVersion "0.3.0"
#define MyAppPublisher "jinyukai8"
#define MyAppExeName "CollegeFinanceManager.exe"

[Setup]
AppId={{A79B46B0-7513-4F35-9A6A-930C14AA67DA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName=D:\CollegeFinanceManager\App
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=D:\CollegeFinanceManager\installer
OutputBaseFilename=CollegeFinanceManager-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#MyAppExeName}
CloseApplications=yes
RestartApplications=no

[Files]
Source: "D:\CollegeFinanceManager\dist\CollegeFinanceManager\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "D:\CollegeFinanceManager\data"
Name: "D:\CollegeFinanceManager\data\backups"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--data-dir ""D:\CollegeFinanceManager\data"""
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--data-dir ""D:\CollegeFinanceManager\data"""; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--data-dir ""D:\CollegeFinanceManager\data"""; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; DATA-001：卸载只移除程序文件，绝不删除 D:\CollegeFinanceManager\data。
