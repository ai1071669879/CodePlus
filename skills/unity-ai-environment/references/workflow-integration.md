# 工作流来源、模式权威与整合取舍

本页供初始化/迁移时比较选择，不作为日常第二份规则。安装后的唯一流程正文是 `Docs/ai/workflow.md`，模式配置是 `Docs/ai/workflow.json`，规则路由仍由 `rules.json` 维护。

## 来源核对

核对日期：2026-10-29。`unity-harness-init` 使用 npm 发布包 **0.1.4** 的 README、coordinator/reviewer、file-partition、TDD 与 workflow 模板；包元数据及 tarball 来自 [npm registry](https://registry.npmjs.org/unity-harness-init/0.1.4)，发布页是 [unity-harness-init](https://www.npmjs.com/package/unity-harness-init)，许可 MIT。未执行其 CLI。它的 README、不同角色文件之间存在快照参数旧示例等差异；实际调用按其固定版本 Unity Skills 模块文档与返回 taskId 核验，不抄旧参数名。

`unity-workflow-kit` 参考 [入口](https://github.com/ZxWyvern/unity-workflow-kit/blob/main/ENTRYPOINT.md)、[运行循环](https://github.com/ZxWyvern/unity-workflow-kit/blob/main/core/06-operating-loop.md)、[证据与失效](https://github.com/ZxWyvern/unity-workflow-kit/blob/main/core/04-evidence-claims-and-invalidation.md) 和 [刷新策略](https://github.com/ZxWyvern/unity-workflow-kit/blob/main/core/07-refresh-policy.md)。研究时入口自报 v1.4.0 beta；不宣称真实项目 token 收益。本包没有复制其 helper 或知识库。

## 模式与冲突处理

| 机制 | 原生模式 | unity-harness-init 模式 |
| --- | --- | --- |
| 规划与实现 | 现有任务分级、结构差异表与按需简报 | 上游 Grill/PRD/Issues → Plan/Implement/Verify/Document；Harness 合同、文件分区与 `/fleet` |
| 测试与评审 | 按风险选测试与独立验证 | 必须 TDD；Reviewer 无源码编辑，开发/评审使用不同模型系列 |
| Editor 工具 | 使用者选择所需桥接，可全部暂缓 | Unity Skills REST 必需；其他桥接不能代替它 |
| 状态权威 | Tasks/index.json | docs/harness/progress.md；Tasks 只作接力记录，不再维护任务状态 |
| 重构契约 | 原 Keep/Rewrite/Forbidden/Superseded 及机器门禁 | 上游 Harness 合同优先；原契约检查只在合同明确引用时辅助使用 |
| 初始化与权限 | 不覆盖已有内容，按维护者授权 | 同样保留；模式优先不授予发布、账户、跨路径或凭据权限 |
| 缺少依赖 | 保持未配置，完成不依赖它的准备 | 前置检查返回未验证，禁止跳过 REST、替换 runner 或降级评审后声称 Harness 就绪 |

`assets/workflows/unity-harness-init/` 是仅在选中时使用的覆盖资产，实际替换 project-rules、workflow、README、任务模板、规划和质量流程等冲突正文，并更新规则源。另一模式资产不复制到目标项目。所有模式共享身份/路径、敏感内容、生成物、工程事实与原始证据要求；选择模式不改用户权限。已存在的 `.github`、Claude、Cursor 等项目入口先盘点，处理其冲突后才启用新宿主流程。

## 从 workflow-kit 采用的内容

- 路线按 ID/别名或文件路径定位，复用现有 context-index；不再生成平行的 agent.md、project-context、index 或 validation-matrix。
- 按分支/执行者记录接力，下一动作附可执行验收；原生模式回填任务正文或该任务关联的独立笔记，Harness 模式由 Coordinator 更新 progress 并链接执行者笔记。
- 源码、序列化接线、运行证据分开；源码/资源/版本/构建/工具链变化后只重核受影响事实，不把历史运行结果自动继承到新环境。
- 任务围绕可观察结果形成完整切片。源码 skeleton/YAML 简化器、第二份 claim-ID 图、自动 Git hooks、`merge=ours` 和外部编译替代 Unity 验收均不导入，避免增加维护面或削弱既有规则。

## 对 Harness 模式的适配边界

保留其强制依赖、角色职责、交叉模型、阶段、文件分区、快照 taskId、维护窗口与错误记录。`/fleet` 与 slash command 只有实际安装到受支持宿主后才可执行；生成模式文档不是安装证明。npm CLI 默认复制 `.github`，不创建运行时 docs/harness，本包仅提供初始 progress 文档，不伪造已完成任务。

上游的 `--force` 覆盖、未经核对的自动回滚及默认挂钩不自动执行：先预览变更范围，保留已有工作，再在任务授权内应用。失败先记录事实与影响，回滚只针对已登记的当前快照范围，不能撤销并行工作者的改动。实际模型、REST 权限和网络数据边界另行验证。
