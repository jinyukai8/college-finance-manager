#define MyAppName "实验室账本"
#define MyAppVersion "0.4.5"
#define MyAppPublisher "jinyukai8"
#define MyAppExeName "CollegeFinanceManager.exe"

[Setup]
AppId={{A79B46B0-7513-4F35-9A6A-930C14AA67DA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableDirPage=no
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
Name: "{code:GetDataDir}"
Name: "{code:GetDataDir}\backups"

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--data-dir ""{code:GetDataDir}"""
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Parameters: "--data-dir ""{code:GetDataDir}"""; Tasks: desktopicon

[InstallDelete]
; 品牌更名后清理旧名称快捷方式，不涉及程序数据或账本数据。
Type: files; Name: "{autoprograms}\学院组织资金管理助手.lnk"
Type: files; Name: "{autodesktop}\学院组织资金管理助手.lnk"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "快捷方式："; Flags: unchecked

[Registry]
; 记住用户选择的数据目录，升级时继续使用；卸载不会删除该目录或其中数据。
Root: HKCU; Subkey: "Software\jinyukai8\LaboratoryLedger"; ValueType: string; ValueName: "DataDir"; ValueData: "{code:GetDataDir}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Parameters: "--data-dir ""{code:GetDataDir}"""; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; DATA-001：卸载只移除程序文件，绝不删除用户选择的账本数据目录。

[Code]
var
  DataDirPage: TInputDirWizardPage;
  DataDirUsesInstallSuggestion: Boolean;

function ExistingDataDirectory(): String;
var
  RememberedDirectory: String;
begin
  Result := '';
  if RegQueryStringValue(
       HKCU,
       'Software\jinyukai8\LaboratoryLedger',
       'DataDir',
       RememberedDirectory
     ) and (Trim(RememberedDirectory) <> '') then
  begin
    Result := RememberedDirectory;
    exit;
  end;

  { 兼容 0.4.3 及更早版本的固定 D 盘正式数据目录。 }
  if FileExists('D:\CollegeFinanceManager\data\finance.db') or
     DirExists('D:\CollegeFinanceManager\data\attachments') then
    Result := 'D:\CollegeFinanceManager\data';
end;

procedure InitializeWizard;
var
  ExistingDirectory: String;
begin
  DataDirPage := CreateInputDirPage(
    wpSelectDir,
    '选择账本数据位置',
    '账本数据库、凭证和备份保存在哪里？',
    '请选择空间充足且会定期备份的位置。升级现有版本时，请保留原数据目录。',
    False,
    SetupMessage(msgNewFolderName)
  );
  DataDirPage.Add('账本数据目录：');

  ExistingDirectory := ExistingDataDirectory();
  DataDirUsesInstallSuggestion := ExistingDirectory = '';
  if DataDirUsesInstallSuggestion then
    DataDirPage.Values[0] := AddBackslash(WizardDirValue()) + 'data'
  else
    DataDirPage.Values[0] := ExistingDirectory;
end;

procedure CurPageChanged(CurPageID: Integer);
begin
  if (CurPageID = DataDirPage.ID) and DataDirUsesInstallSuggestion then
    DataDirPage.Values[0] := AddBackslash(WizardDirValue()) + 'data';
end;

function NextButtonClick(CurPageID: Integer): Boolean;
begin
  Result := True;
  if CurPageID = DataDirPage.ID then
  begin
    if Trim(DataDirPage.Values[0]) = '' then
    begin
      MsgBox('请选择账本数据目录。', mbError, MB_OK);
      Result := False;
      exit;
    end;
    DataDirUsesInstallSuggestion := False;
  end;
end;

function GetDataDir(Param: String): String;
begin
  Result := RemoveBackslashUnlessRoot(ExpandFileName(DataDirPage.Values[0]));
end;
