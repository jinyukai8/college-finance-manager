# 实验室账本

面向单人使用的 Windows 本地离线辅助账本。V1 使用 Python 3.12、PySide6 和 SQLite，数据与安装目录分离。

当前版本 0.4.10：程序安装位置和账本数据位置可分别选择。直接双击程序和从快捷方式打开均使用已配置的账本。双击业务单元格可编辑，可查看更正历史、冲销及管理发票。支付方式在录入、编辑和详情中使用，列表不展示。报销、预付款、报表仅从导航隐藏。

记录总数按已应用筛选统计所有页，已选数统计本页勾选；账本总余额仍在“总览”查看。

## 安装与使用

安装向导里可分别选择程序文件和账本数据的位置。升级时请沿用已有数据目录。另选数据目录只会切换程序打开的位置，旧账本和凭证不会自动搬家；需要迁移时，请先创建并验证完整备份，再通过应用的备份恢复功能迁移。卸载保留账本及凭证。

安装版优先使用对应程序目录旁的启动配置，兼容旧安装保存的账户级配置。首次运行未配置的程序时，请按提示选择已有账本位置或新建账本位置。命令行的 `--data-dir` 可临时指定位置，适用于隔离开发和测试。

## 本机开发、测试和构建

需要 Python 3.12。在源码目录通过 PowerShell 运行以下命令。可把示例中的 `-DeployRoot` 改成任意可写目录，也可以省略此参数，使用源码下的 `build\windows`。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 -DeployRoot 'E:\LedgerBuild'
powershell -ExecutionPolicy Bypass -File .\scripts\run.ps1 -DeployRoot 'E:\LedgerBuild'
powershell -ExecutionPolicy Bypass -File .\scripts\test.ps1 -DeployRoot 'E:\LedgerBuild'
```

开发启动默认使用所选构建目录下的 `test-data`，也可通过 `run.ps1 -DataDir` 指定独立数据目录。自动化测试使用 pytest 的临时目录。旧的 `*_d_drive.ps1` 文件仍可调用，目录参数与新命令一致。

0.4.4 已贯通数据库初始化、直接收支、冲销与作废、可审计日期更正、报销、预付款、发票/凭证、Excel 报表、核对、自动与手动备份、安全恢复、单实例保护和 Windows 安装。界面采用统一的品牌侧栏、余额主卡、业务指标卡、按钮、输入框及表格主题；收支支持可选物品、录入时提交发票、发票状态显示和只读回收站。筛选结果可导出为实验室采购账本版式，金额区域按约定留空供手工填写。价格使用数值常规显示，整数不显示多余小数点。正式使用前请先创建一份手动备份，并定期把备份复制到另一存储设备。

生成 Windows 程序：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1 -DeployRoot 'E:\LedgerBuild'
```

生成安装程序需先安装 Inno Setup 6。若 Inno Setup 装在自定义位置，用 `-CompilerPath` 指定 `ISCC.exe`。

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1 -DeployRoot 'E:\LedgerBuild'
```

程序构建产物位于所选目录的 `dist\CollegeFinanceManager`，安装包位于 `installer`，构建临时文件和缓存位于 `build`。构建命令只生成文件，安装位置与账本位置由安装向导另行选择。
