# Harness 模式项目入口

先读 [workflow.md](workflow.md) 的配置、阶段和冲突屏蔽，再读 [共同工程边界](project-rules.md)、`project-adaptation.md`（项目适配）、`project-profile.json`（profile）、`access-policy.json`（policy） 与命中导航。规则源由 [rules.json](rules.json) 唯一定位。

- 当前模式：`workflow.json`（workflow.json）；工具/模式目录：`setup-options.json`（setup-options.json）。
- 前置检查：`python tools/ai/project_setup.py list` / `check`。缺 REST、上游模板、Copilot /fleet 或交叉模型时停止相关执行；不降级原生流程。
- 环境结构：`python tools/ai/check_env.py check`；此命令不认证 Harness 已连接或可执行。
- 导航：`python tools/ai/context.py --paths <相对路径>`；`context-index.json`（context-index） 与 [字段合同](configuration.md)。
- 任务/迭代状态唯一在 `docs/harness/progress.md`；合同/报告按已核验上游模板。Tasks/index.json 保持空任务表，仅允许从 progress 链接执行者接力笔记。
- Unity 内容安全：`unity-rules.md`（unity-rules）、[策划/配置/事件图](planning-workflows.md)、`audit-capabilities.md`（审计证据）。
- 工具配方：[unity-tooling](unity-tooling.md)、`tool-integrations.md`（工具信任）；辅助评测/架构：[quality-workflows](quality-workflows.md)。

初始化不运行 npm/Editor，不伪造 REST 连接或角色加载；实际验证后才填写能力证据。保留已有权限与工作区改动。切换模式前先预览并迁移状态/宿主入口；冲突整批不写。
