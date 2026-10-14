# 学院组织资金管理助手

面向单人使用的 Windows 本地离线辅助账本。V1 使用 Python 3.12、PySide6 和 SQLite，数据与安装目录分离。

## D 盘部署与运行

本项目按当前部署约定把虚拟环境、应用数据、备份和构建产物放在 `D:\CollegeFinanceManager\`。在源码目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_d_drive.ps1
powershell -ExecutionPolicy Bypass -File .\scripts\run_d_drive.ps1
```

脚本不会删除或覆盖已有正式数据库。若 `D:\CollegeFinanceManager\data\finance.db` 已存在，只会执行向前迁移。

## 开发运行

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.lock
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m college_finance_manager
```

运行测试：

```powershell
.\.venv\Scripts\python -m pytest
```

产品默认数据位置仍遵循规范使用 `%LOCALAPPDATA%\CollegeFinanceManager\`；本项目的部署脚本显式指定 `D:\CollegeFinanceManager\data\`，因此实际数据保存在 D 盘。测试必须使用 pytest 提供的临时目录，禁止指向正式目录。

0.4.0 已贯通数据库初始化、直接收支、冲销与作废、报销、预付款、发票/凭证、Excel 报表、核对、自动与手动备份、安全恢复、单实例保护和 Windows 安装。收支支持可选物品、录入时提交发票、发票状态显示和只读回收站；筛选结果可导出为实验室采购账单版式，金额区域按约定留空供手工填写。正式使用前请先创建一份手动备份，并定期把备份复制到另一存储设备。

Windows 构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```

生成可卸载安装程序（需要 Inno Setup 6）：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_installer.ps1
```

安装包输出到 `D:\CollegeFinanceManager\installer\`，默认把程序安装到 `D:\CollegeFinanceManager\App`，数据保存在 `D:\CollegeFinanceManager\data`。卸载程序不会删除数据目录。
