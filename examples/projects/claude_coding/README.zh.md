# Claude-Code-like 独立审查

状态：开发中，尚未完成课程资格验证。下列源码是工作实现，不是已通过 3×3 真实矩阵的发布承诺。基础机制与已发生的结果见[实施记录](../../../docs/internal/plans/agent_design_lab_execution.md)。

## 原始思想与改编边界

收集项目上下文、编辑、验证，再请求作用域独立的审查。本课不复刻专有行为，也不是文件回滚服务。 [原始来源](https://code.claude.com/docs/en/how-claude-code-works)。

## 框架与用户的分工

ReviewBoundary 在验证后请求安全暂停；DurableWorkRuntime 负责 spawn/join 和 Session restore。审查者有独立 Session 和受限注册表，审查意见不授予父环境写权限。

QitOS 已提供：模型事务与 usage、工具权限/校验、Env 执行、Session、ArtifactRef 和 Trajectory。用户编写：任务、策略、完成检查及记忆/技能选择。本轮补齐：自定义 agent_factory 接入、持久技能版本、完整正文加载、显式 Memdir 删除与产物引用的数据权限修正。

核心增量位于完整源码中的 agent.py；CLI 负责显式配置与资源生命周期，evaluate.py 是控制端检查器。任务由项目自有合成材料组成，不是论文基准或真实客户数据。

## 安装、配置与运行

先按仓库构建说明安装本轮 QitOS wheel（当前 PyPI 版本不能替代未发布实现），再安装本课程。真实地址与凭据仅放在仓库外。模型配置采用完整 qitos.agent 文件，课程只读取其中 model；不是通过环境变量注入 key。

每次 run 使用新的仓库外目录；resume 只接受同一项目重构的工厂与 resolver。

默认输出上限 10,240，可通过私有模型配置提高；单任务步数、请求数和运行时间读取公开配置。validate 不调用模型，真实执行必须显式 --live。Docker 不可用时不能降级到宿主。模型失败、未完成任务和人工干预均保留，不能自动改为通过。

## 验证、练习与组合

独立检查器核验资料/数值或实际代码结果，不接受模型自报成功。计划修订、技能实际加载、子 Session 身份与失败也须单独验收。Session 恢复不是文件回滚；生成代码只在受限 Env 内执行。

练习：替换为兼容性审查策略，保留子身份和结果返回证据。

组合：复用 Pi 检查器，再把 Hermes 流程作为按需上下文接入，不增加执行循环。

完整矩阵：三种任务各三轮。ReAct/PlanAct 使用同样任务；PlanAct 的 static、Hermes 的 no-memory、Voyager 的 no-skills 是明确对照，不以一次成功作性能结论。私有原始轨迹不能直接公开；仅在检查许可与脱敏后发布衍生摘要。

```bash
python -m pip install .
python -m qitos_lab_claude validate --config agent.yaml --root /tmp/lab-validation
python -m qitos_lab_claude run --config agent.yaml --model-config /private-config/model.yaml --credentials /private-config/credentials.yaml --root /private-runs/claude-attempt --task 0 --live
```


