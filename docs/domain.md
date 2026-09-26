# 领域约定

描述疗愈服务宣传、资质边界、跨主体履约和消费争议的事件契约与领域规则。

聚合对象包括`service_provider`、`wellness_offer`、`marketing_claim`、`consumer_case`、`consent`、`complaint`、`payment`。所有发生时间都必须携带时区，版本号按聚合从 1 开始递增，基础校验不会改写调用方输入。

## 案卷登记项

`CaseFile`（`casefile.py`）把以下材料登记到同一案卷：经营主体与从业资质（`registry.py`）、服务包版本与价格构成（`offers.py`）、宣传主张及证据（`claims.py`）、知情确认（`consent.py`）、风险筛查、服务记录、转介提示、合同变更（`records.py`）和争议材料（证据库与投诉台）。

## 领域规则

- **审查职责分离**：平台审核只能确认上架信息；风险边界由专业审查决定；商家及其所属机构的人员不得批准自己的功效表述。每条宣传都可判定是否超出经营主体许可（普通体验 / 心理支持 / 医疗诊疗）。
- **同意撤回**：消费者撤回同意后停止未来服务与新用途；既有履约和争议证据依法保留，仅履约、争议、监管目的可访问。
- **跨方责任**：一次订单可跨越多个地区和经营方；转包只改变履约方，责任仍归原责任方。
- **投诉去重**：投诉号与材料指纹（合同、金额、材料摘要）都相同的重复投诉沿用原回执；投诉号相同但指纹不同的单独核查并关联原回执。
- **资金幂等**：冻结、退款、保证金扣划按幂等键去重，相同键不同参数视为冲突；各自不得超过订单实收或保证金余额，避免并发重复执行。
- **期限引擎**：冷静期、补证、整改、退款期限使用可控时钟；服务暂停时冻结剩余时间，恢复后继续原有倒计时。
- **查询视图**：监管接口展示每条宣传是否超出许可、各方尚未履行的义务；消费者查询只获得最小必要案情和明确责任方；最终处理可追溯到当时有效的规则版本与完整证据链。

## 事件载荷

- `CLAIM_SCREENED`：载荷还需包含 `rule_version`, `review_scope`（`listing` 或 `risk_boundary`）。
- `CASE_OPENED`：载荷还需包含 `contract_snapshot`, `evidence_hashes`。
- `CONSENT_WITHDRAWN`：载荷还需包含 `consent_ref`。
- `COMPLAINT_RECEIPTED`：载荷还需包含 `complaint_no`, `receipt_no`, `fingerprint`。
- `COMPLAINT_SPLIT`：载荷还需包含 `complaint_no`, `receipt_no`, `linked_to`。
- `FUNDS_HELD` / `REFUND_ISSUED`：载荷还需包含 `order_ref`, `amount_cents`, `idempotency_key`。
- `DEPOSIT_DEDUCTED`：载荷还需包含 `obligor_ref`, `amount_cents`, `idempotency_key`。
- `DEADLINE_PAUSED` / `DEADLINE_RESUMED`：载荷还需包含 `case_ref`, `deadline_kind`。
- `OBLIGATION_FULFILLED`：载荷还需包含 `obligation_ref`, `obligor_ref`。
- `REMEDY_EXECUTED`：载荷还需包含 `obligor_ref`, `amount`。
- `DISPOSITION_RECORDED`：载荷还需包含 `outcome`, `rule_version`, `evidence_hashes`。

相同事件标识的业务幂等、冲突隔离和状态推进由案卷聚合按上述规则负责；契约只定义可稳定交换的基础事实。
