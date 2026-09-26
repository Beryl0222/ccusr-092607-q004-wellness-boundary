# 疗愈服务合规边界案卷

描述疗愈服务宣传、资质边界、跨主体履约和消费争议的事件契约，并实现对应的领域规则。

## 目录

- `contracts/domain.schema.json`：对象、事件和载荷字段约定。
- `data/sample.json`、`data/sample_disposition.json`：可直接校验的联调样例。
- `src/wellness_boundary/`：契约校验、命令行入口与领域模块：
  - `registry.py`：经营主体、从业资质与审查人员登记。
  - `claims.py`：宣传审查职责分离（平台/专业/商家）与超许可判定。
  - `consent.py`：知情确认、撤回与证据限制访问。
  - `offers.py`：服务包版本与价格构成。
  - `records.py`：风险筛查、服务记录、转介提示、合同变更。
  - `responsibility.py`：跨地区跨经营方责任链。
  - `complaints.py`：投诉回执沿用与单独核查。
  - `funds.py`：冻结、退款、保证金扣划的幂等台账。
  - `deadlines.py` + `clock.py`：可控时钟与期限引擎。
  - `casefile.py` + `views.py`：案卷聚合、监管/消费者视图与追溯。
- `tests/`：信封、时间、版本、事件载荷与全部领域规则测试。
- `docs/domain.md`：领域对象、规则与事件语义。

## 测试

```bash
python3 -m unittest discover -s tests
```

## 编译检查

```bash
python3 -m compileall -q src tests
```

## 样例校验

```bash
PYTHONPATH=src python3 -m wellness_boundary.cli contracts/domain.schema.json data/sample.json
```

样例有效时输出 `valid`；发现问题时逐行给出字段、代码和中文说明，并返回非零状态。
