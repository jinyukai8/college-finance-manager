#define MyAppName "实验室账本"
#define MyAppVersion "0.4.10"
#define MyAppPublisher "jinyukai8"
#define MyAppExeName "CollegeFinanceManager.exe"
#ifndef BuildSourceDir
  #error Pass the application build directory as /DBuildSourceDir or use scripts/build_installer.ps1.
#endif
#ifndef InstallerOutputDir
  #error Pass the installer output directory as /DInstallerOutputDir or use scripts/build_installer.ps1.
#endif

[Setup]
AppId={{A79B46B0-7513-4F35-9A6A-930C14AA67DA}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableDirPage=no
UsePreviousAppDir=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir={#InstallerOutputDir}
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
Source: "{#BuildSourceDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Dirs]
Name: "{code:GetDataDir}"; Flags: uninsneveruninstall
Name: "{code:GetDataDir}\backups"; Flags: uninsneveruninstall

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Check: CreateOrRefreshDesktopShortcut

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
Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Description: "启动{#MyAppName}"; Flags: nowait postinstall skipifsilent unchecked

[UninstallDelete]
; DATA-001：卸载只移除程序文件，绝不删除用户选择的账本数据目录。
Type: files; Name: "{app}\ledger-paths.ini"

[Code]
const
  DriveRemovable = 2;
  DriveFixed = 3;
  MoveFileReplaceExisting = 1;

var
  DataDirPage: TInputDirWizardPage;
  SelectedAppDirectory: String;
  PreviousDataDir: String;

function GetDriveType(DriveRoot: String): Cardinal;
  external 'GetDriveTypeW@kernel32.dll stdcall';

function ReplaceFilePath(OldFile, NewFile: String; Flags: Cardinal): Boolean;
  external 'MoveFileExW@kernel32.dll stdcall';

function CreateOrRefreshDesktopShortcut(): Boolean;
begin
  { 已有快捷方式需要刷新，避免旧参数覆盖本次选择。 }
  Result := WizardIsTaskSelected('desktopicon') or
    FileExists(ExpandConstant('{autodesktop}\{#MyAppName}.lnk'));
end;

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
  if FileExists('D:\CollegeFinanceManager\data\finance.db') then
    Result := 'D:\CollegeFinanceManager\data';
end;

function DataDirectoryForProgram(AppDirectory: String): String;
var
  Lines: TArrayOfString;
  I: Integer;
begin
  Result := '';
  { 读取本安装器生成的 UTF-8 路径配置，优先保留这份安装自己的账本。 }
  if LoadStringsFromFile(AddBackslash(AppDirectory) + 'ledger-paths.ini', Lines) then
    for I := 0 to GetArrayLength(Lines) - 1 do
      if CompareText(Copy(Lines[I], 1, 8), 'DataDir=') = 0 then
      begin
        Result := Trim(Copy(Lines[I], 9, Length(Lines[I])));
        exit;
      end;
end;

procedure SuggestDataDirectory;
begin
  SelectedAppDirectory := WizardDirValue();
  PreviousDataDir := DataDirectoryForProgram(SelectedAppDirectory);
  if PreviousDataDir = '' then
    PreviousDataDir := ExistingDataDirectory();
  if PreviousDataDir = '' then
    DataDirPage.Values[0] := AddBackslash(SelectedAppDirectory) + 'data'
  else
    DataDirPage.Values[0] := PreviousDataDir;
end;

procedure InitializeWizard;
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
  SuggestDataDirectory;
end;

function ValidDataDirectory(Directory: String): Boolean;
var
  DriveType: Cardinal;
begin
  Result := False;
  if Length(Directory) < 3 then
    exit;
  if (Directory[2] <> ':') or (Directory[3] <> '\') or
     PathHasInvalidCharacters(Directory, True) or FileExists(Directory) then
    exit;
  DriveType := GetDriveType(Copy(Directory, 1, 3));
  Result := (DriveType = DriveFixed) or (DriveType = DriveRemovable);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  SelectedDirectory: String;
begin
  Result := True;
  if (CurPageID = wpSelectDir) and not PathSame(SelectedAppDirectory, WizardDirValue()) then
    SuggestDataDirectory;
  if CurPageID = DataDirPage.ID then
  begin
    SelectedDirectory := PathNormalizeSlashes(Trim(DataDirPage.Values[0]));
    if not ValidDataDirectory(SelectedDirectory) then
    begin
      SuppressibleMsgBox('请选择本机可用磁盘上的完整文件夹路径。', mbError, MB_OK, IDOK);
      Result := False;
      exit;
    end;
    SelectedDirectory := RemoveBackslashUnlessRoot(ExpandFileName(SelectedDirectory));
    if (PreviousDataDir <> '') and
       not PathSame(SelectedDirectory, RemoveBackslashUnlessRoot(ExpandFileName(PreviousDataDir))) then
    begin
      if WizardSilent() then
        Result := False
      else
        Result := SuppressibleMsgBox(
          '原账本目录：' + PreviousDataDir + #13#10 +
          '新账本目录：' + SelectedDirectory + #13#10#13#10 +
          '原账本和凭证会留在原目录，新版将打开新目录。' +
          '如果要继续使用原账本，请选择“否”并保留原目录。确认切换？',
          mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO
        ) = IDYES;
      if not Result then
        exit;
    end;
    DataDirPage.Values[0] := SelectedDirectory;
  end;
end;

function GetDataDir(Param: String): String;
begin
  Result := RemoveBackslashUnlessRoot(ExpandFileName(DataDirPage.Values[0]));
end;

function UpdateReadyMemo(Space, NewLine, MemoUserInfoInfo, MemoDirInfo, MemoTypeInfo,
  MemoComponentsInfo, MemoGroupInfo, MemoTasksInfo: String): String;
begin
  Result := MemoDirInfo + NewLine + NewLine + '账本数据位置：' + NewLine +
    Space + GetDataDir('') + NewLine + NewLine + MemoTasksInfo;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigPath, TemporaryPath: String;
  Contents: TArrayOfString;
begin
  if CurStep <> ssPostInstall then
    exit;
  ConfigPath := ExpandConstant('{app}\ledger-paths.ini');
  TemporaryPath := GenerateUniqueName(ExpandConstant('{app}'), '.tmp');
  SetArrayLength(Contents, 2);
  Contents[0] := '[Paths]';
  Contents[1] := 'DataDir=' + GetDataDir('');
  if not SaveStringsToUTF8File(TemporaryPath, Contents, False) then
  begin
    DeleteFile(TemporaryPath);
    RaiseException('无法保存账本数据目录。');
  end;
  if not ReplaceFilePath(TemporaryPath, ConfigPath, MoveFileReplaceExisting) then
  begin
    DeleteFile(TemporaryPath);
    RaiseException('无法更新账本数据目录。');
  end;
end;
