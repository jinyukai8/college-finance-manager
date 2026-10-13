# 架构说明

```text
ui -> application -> domain
          |
          v
   infrastructure
```

- `ui`：PySide6 页面、对话框与只读视图模型；禁止 SQL 与余额计算。
- `application`：用例边界、事务、幂等协调与 DTO。
- `domain`：金额、状态机、余额及业务不变量；不依赖 Qt 或 SQLite。
- `infrastructure`：SQLite、迁移、文件、凭证、备份、导出、系统路径和单实例锁。

SQLite 连接统一启用外键、WAL、忙等待和安全同步。数据库有顺序迁移版本；新迁移只前进，不改写已发布脚本。V1 只有一个账本，但所有业务表保留 `ledger_id`。

默认数据根目录为 `%LOCALAPPDATA%\CollegeFinanceManager\`：

```text
finance.db
attachments/
backups/
logs/
app.lock
```

自动测试通过显式 `data_dir` 使用临时目录。应用代码不得以“找不到测试标志”为由退回正式目录。

当前机器的部署约定使用命令行显式覆盖：运行环境 `D:\CollegeFinanceManager\.venv\`、数据 `D:\CollegeFinanceManager\data\`、构建产物 `D:\CollegeFinanceManager\dist\`。这样不改变产品的通用默认规则，同时保证本机实际内容落在 D 盘。
