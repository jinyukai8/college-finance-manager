# 数据库设计

数据库为 SQLite，金额字段均为 `INTEGER` 分，业务主键为 UUID 文本，日期为本地 `YYYY-MM-DD`，操作时间为带时区 ISO 8601 文本。

## 表与关系

- `ledgers`：账本和不可直接覆盖的期初数据。
- `categories`：账本内收入/支出类别；引用后停用而非删除。
- `transactions`：现金流水，含编号、方向、类别快照、状态、来源、冲销关系和幂等键。
- `reimbursements`：报销申请；`payment_transaction_id` 唯一关联实际支出。
- `advances`：预付款主记录；`payment_transaction_id` 唯一关联支付支出。
- `advance_events`：核销/退款事件；退款流水唯一关联。
- `attachments`：业务对象凭证元数据与 SHA-256。
- `audit_logs`：仅追加的业务操作摘要和原因。
- `reconciliations`：账面额与人工核对额及差额。
- `settings`：账本设置；`schema_migrations`：已应用迁移及校验和。

## 关键约束

- 外键强制开启；流水、申请、预付款金额均大于零。
- 枚举字段用 `CHECK` 限定；名称、用途等必要文本禁止空白。
- 业务编号在账本内唯一；幂等键全局唯一。
- 报销和预付款的关联支付流水使用部分唯一索引防重复。
- 常用查询按账本+日期、状态、类别建立索引。
- 跨表累计约束（如预付款剩余额）由应用事务验证，并由集成测试覆盖。

详细定义以不可变迁移脚本 `0001_initial.sql` 为准。
