# 领域约定

描述疗愈服务宣传、资质边界、跨主体履约和消费争议的事件契约。

聚合对象包括`service_provider`、`wellness_offer`、`marketing_claim`、`consumer_case`。事件类型包括`OFFER_VERSIONED`、`CLAIM_SCREENED`、`CONSENT_RECORDED`、`CASE_OPENED`、`REMEDY_EXECUTED`。所有发生时间都必须携带时区，版本号从 1 开始递增，基础校验不会改写调用方输入。

## 事件载荷

- `CLAIM_SCREENED`：载荷还需包含 `rule_version`, `review_scope`。
- `CASE_OPENED`：载荷还需包含 `contract_snapshot`, `evidence_hashes`。
- `REMEDY_EXECUTED`：载荷还需包含 `obligor_ref`, `amount`。

相同事件标识的业务幂等、冲突隔离和状态推进由上层服务负责；本仓库只定义可稳定交换的基础事实。
