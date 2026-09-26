# 案卷服务层语义

契约层（`contracts/`）只定义可稳定交换的基础事实；本层承担领域约定中交给上层
服务的业务幂等、冲突隔离和状态推进，模块位于 `src/wellness_boundary/`。

## 案卷登记

`CaseFile` 登记一单争议的全部材料：经营主体与从业资质（`ProviderProfile` /
`Qualification`）、服务包版本（`OfferVersion`）、宣传主张及证据
（`MarketingClaim` / `Evidence`）、价格构成（`PriceBreakdown`）、知情确认
（`ConsentRecord`）、风险筛查（`RiskScreening`）、服务记录（`ServiceRecord`）、
转介提示（`ReferralNotice`）、合同变更（`ContractChange`）和争议材料
（`DisputeMaterial`）。`CaseBook` 负责开案并接线期限引擎与资金台账。

## 审查分离

- 平台审核只能确认上架信息（`ReviewScope.LISTING`）；
- 专业审查负责风险边界（`ReviewScope.RISK_BOUNDARY`）；
- 商家不得批准自己的功效表述：自我批准抛出 `SelfApprovalError`，且商家不是
  任何审查范围的合格审查人。

宣传是否越界由资质上限判定：`qualification_ceiling` 取主体在宣传时点有效的
最高许可分级（普通体验 < 心理支持 < 医疗诊疗），`claim_exceeds_license`
比较宣传分级与许可上限，过期资质不计入。

## 知情撤回

`withdraw_consent` 之后：未履约的服务记录一律取消（停止未来服务）；履约与
争议之外用途的新材料被拒绝（停止新用途）；既有履约记录与争议证据依法保留，
并标记 `access_restricted` 限制访问。

## 投诉受理

`complaint_fingerprint` 以合同快照、金额与材料指纹计算事实指纹。同一投诉号
且指纹一致的重投沿用原回执（`Receipt.reused=True`）；投诉号相同但合同、金额
或材料指纹任一不同的，单独核查另开案卷。受理加锁，并发重投只开一案。

## 资金操作幂等

`RemedyLedger` 处理冻结、退款、保证金扣划：同一幂等键内容一致的重投返回首次
记录（`replayed=True`）不重复入账；同键不同内容拒绝；每类操作可设案卷级额度
上限（退款不超过实收、扣划不超过保证金）；每个案卷一把锁，并发提交串行化。

## 期限引擎

`DeadlineEngine` 以注入的 `Clock` 处理冷静期、补证、整改和退款。`pause`
冻结倒计时（服务暂停），`resume` 继续原有倒计时——剩余期限不因暂停重置，
暂停时长不计入已耗时间；到期判定只在运行中进行。

## 责任链与义务

`ChainLink` 记录跨地区、跨经营方的订单责任链（销售方/平台/分包方）。
`delegate_obligation` 只登记执行转包（`delegated_to`），责任方
（`obligor_ref`）不变——责任不因转包而丢失。

## 查询与追溯

- `regulator_view`：每条宣传是否超出许可、各方尚未履行的义务（含转包注记与
  期限剩余）、责任链、证据与资金操作全貌；
- `consumer_view`：最小必要案情与明确责任方，仅限本人查询，不暴露内部审查
  意见与他人材料；
- `trace_disposition`：从最终处理追溯当时有效的规则版本（`RuleBook` 按作出
  时点判定）与完整证据链、事件链。

## 事件日志

`EventLog` 在登记前以契约校验事件：相同事件标识且内容一致的重投幂等返回；
同标识不同内容拒绝（冲突隔离）；同一聚合版本号严格递增（状态推进）。
