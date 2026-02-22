# 发布准备清单

## 目标

确保 QitOS 作为开源框架发布时，既能跑，也能被长期信任和复用。

## P0 必须满足

1. 核心接口冻结并文档化。
2. 示例可运行且与文档一致。
3. hook payload 契约稳定并有测试。
4. trace schema 稳定并有测试。
5. 公共 API 导出面无泄漏。

## P1 建议满足

1. 中英文教程链路完整。
2. 竞品对比内容客观且可验证。
3. `qita` board/replay 使用文档完整。
4. 提供最小回归任务集与脚本。

## Source Index

- [PRD.md](https://github.com/Qitor/qitos/blob/main/PRD.md)
- [plans.md](https://github.com/Qitor/qitos/blob/main/plans.md)
- [qitos/__init__.py](https://github.com/Qitor/qitos/blob/main/qitos/__init__.py)
- [qitos/engine/__init__.py](https://github.com/Qitor/qitos/blob/main/qitos/engine/__init__.py)
- [tests/test_p0_freeze_guards.py](https://github.com/Qitor/qitos/blob/main/tests/test_p0_freeze_guards.py)
