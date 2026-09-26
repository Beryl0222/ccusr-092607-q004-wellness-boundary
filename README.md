# 疗愈服务合规边界案卷

描述疗愈服务宣传、资质边界、跨主体履约和消费争议的事件契约，并提供案卷服务层。

## 目录

- `contracts/domain.schema.json`：对象、事件和载荷字段约定。
- `data/sample.json`：可直接校验的联调样例。
- `src/wellness_boundary/`：契约校验、案卷聚合、审查分离、投诉受理、资金幂等、期限引擎与查询视图。
- `tests/`：信封、时间、版本、事件载荷与服务层规则测试。
- `docs/domain.md`：领域对象与事件语义。
- `docs/service.md`：案卷服务层语义（幂等、撤回、期限、责任链、查询与追溯）。

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
