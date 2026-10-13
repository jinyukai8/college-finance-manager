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

当前代码已完成 A→E 的首轮贯通：数据库与初始化、直接收支、冲销与作废、报销和预付款核心用例、凭证导入、Excel 报表、核对、完整备份恢复以及 Windows 构建。报销、预付款、凭证、报表和恢复的图形界面仍需在下一轮补齐，详见 `KNOWN_ISSUES.md`；当前版本不得直接用于正式记账。

Windows 构建：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\build_windows.ps1
```
