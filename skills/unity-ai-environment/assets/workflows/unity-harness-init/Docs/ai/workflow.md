# Unity Harness 长期迭代模式

<!-- ai-rule: workflow -->

当前 `workflow.json`（workflow.json） 的 mode 为 `unity-harness-init`。本模式依据 npm `unity-harness-init@0.1.4`，选用后按其规定流程执行；与原生模式冲突的任务分级、规划格式、原生契约前置和 Tasks 任务状态均已停用。本页不将缺依赖的 Harness 降级为另一种流程。用户范围、凭据、既有更严权限、原始证据和最终接受责任仍适用。

<!-- ai-rule: grading -->

已有项目先 `/scout`；新项目可先 brainstorming/expand。新功能进入发现阶段 `/grill-me` → `/write-a-prd` → `/prd-to-issues`，收敛设计、形成 PRD 与完整垂直职责切片；已有明确需求沿上游允许的入口进入开发阶段，不机械制造第二份需求。对外写入 GitHub Issues 先准备可审阅内容并遵守任务授权。

## Harness 配置

<a id="harness-setup"></a>

初始化只选择并生成配置，不安装 npm 包，不连接 Editor。`unity-skills-rest`、`unity-harness-init`、`copilot-cli` 自动标 enabled/required，能力状态保持 unconfigured。运行 `python tools/ai/project_setup.py check`：缺安装文件、版本或验证证据返回 2，必须补齐后才开始对应执行；结构错误返回 1。退出 0 也只是已登记前置齐全，不证明本次 REST 会话在线。

1. 固定 Unity、Unity Skills 包、Harness npm 包、Copilot CLI 的实际兼容版本、来源和许可。先核 [Unity Skills 安装说明](https://github.com/Besty0728/Unity-Skills)，审阅 UPM 包变更；固定 Git tag/commit 后按授权安装，不能用现有 CLI/MCP 代替 REST。
2. 从该固定版本部署 `.github/skills/unity-skills/` 及其 Python helper，按真实模块文档确认端点、身份、权限与 API schema。不能把旧的 localhost:8090、Semi-Auto/Full-Auto 名称或参数当所有版本恒定合同。记录 status 返回的工程/Editor 身份，执行一个已确认只读查询。共享 capability 仅保存 endpoint/版本/证据和环境变量名，本机路径/密钥另存。
3. 审阅 Harness 包再预览导入：`npx --yes unity-harness-init@0.1.4 --target <工作区根> --dry-run`。npx 首次可能下载，只有安装已获授权才执行。检查 `.github` 每项候选；正常导入命令去掉 `--dry-run`，禁止使用 `--force` 覆盖既有规则。冲突逐项合并；npm CLI 不替你安装 Unity Skills，也不创建运行时 progress。
4. 核对 `.github/copilot-instructions.md`、四个核心角色、prompts、templates 与 workflow skills；确保其状态路径与本模式一致。安装可能修改宿主自动入口，先检查原生流程、其它项目规则和 hooks 是否仍会被宿主同时加载，停用冲突入口后新会话验证。不能只依赖本地 `rules.json` 就宣称所有宿主已切换。
5. 配置实际可用的 Copilot CLI、账号和 `/fleet`，按其版本 help 核对语法。Developer 与 Reviewer 必须选不同系列模型，并写进每个 track 的 Model 字段；缺第二模型或宿主不支持 `/fleet` 时保持未验证，不用同模型或串行普通任务冒充。
6. 在 profile.capabilities 填写真实 command/endpoint、固定 version、source_paths/entrypoints、verified_revision/evidence，状态先 located，完成对应工具/宿主/连接验证才改 verified。`environment.py doctor --probe --capability <id>` 只验证已审阅的版本参数，不能代替 MCP/REST 握手或角色实际加载。项目配置检查与在线 status/运行证据分别保存。

三种可选 Editor 桥接仍可在目录中查看，但此模式由 Unity Skills REST 主导 Editor 执行。同 `unity-editor` 组不能同时启用两个提供者；如果另外选择 CLI/Coplay/AnkleBreaker 导致冲突，初始化拒绝整批写入，不悄悄移除强制依赖。

<!-- ai-rule: intent -->

## Plan：合同与文件分区

Planner 负责需求与架构；Coordinator 从已确认规格生成 Harness 任务合同和 `/fleet` prompt，不直接写实现代码。合同使用已导入 `.github/templates/task-contract.md`，运行时放 `docs/harness/contracts/`，记录完整可观察结果、验收、独占文件、禁止文件和依赖。原生 `Tasks/<id>-contract.md` 及 `contract_check.py` 不作为本模式隐含前置；只有 Harness 合同明确引用时才作为辅助检查。

Coordinator 每次任务开始先核 REST 在线身份并按固定版本 workflow 模块创建快照，保存实际返回 taskId。快照名称、参数、结束/回滚签名从真实模块读取，不沿用 README 旧示例硬编码。共享接口先完成，注册、配置、asmdef 和同一场景资源安排唯一写入者；并行 track 的独占范围不能重叠。共享文件系统的提示分区不是隔离边界。

<!-- ai-rule: execution -->

## Implement：/fleet 与 TDD

使用上游 `/plan-iteration` → `/fleet-implement`。Coordinator 按上游轨道建议及实际独立任务生成自包含 prompt；没有足够独立任务时不为凑数拆碎。每个 track 标 Agent、Model、完整背景、精确文件分区、依赖、停止条件和验收；子代理不能依赖 Coordinator 的对话历史。

Developer 严格 Red → Green → Refactor：先在编译正常的前提下看到行为测试失败，最小实现使其通过，再重构并保绿。编译、测试通过 Unity Skills REST 的 debug/test 模块，按真实异步 jobId 轮询结果。纯逻辑走已存在的 EditMode 边界，生命周期/物理/场景交互走合适 PlayMode。沿用目标程序集与依赖制度，不因模板目录或名字直接重建工程。

没有 REST 连接、所需模块被限制或执行来源不明时，停止对应阶段并保留阻碍；不能换成 `unity_checks.py` 读一份手填报告后宣称完成强制流程。

<!-- ai-rule: verification -->

## Verify：独立验收

Reviewer 与 Developer 使用不同模型系列，Reviewer 不修改源码或资源；执行门禁允许产生日志/测试结果等证据。按合同通过 REST 检查编译 → EditMode/相关 PlayMode → console 日志 → 场景/缺失脚本验证 → 代码/设计审查 → 逐项 PASS/FAIL 报告，放 `docs/harness/reports/`。上游 validation 所需权限以固定版本服务制度核对，不为通过而放开无关写权限。

测试执行前后保留源码/测试/配置摘要，非预期变动为验证失败。发布、存档、网络、设备和性能相关判据仍需真实专项证据；编译/场景检查不能代替这些结果。报告保留命令、退出码、范围、失败与未运行项，最终是否接受由实际负责人决定。

<!-- ai-rule: tracking -->

## Document、恢复与维护

Coordinator 更新唯一状态源 `docs/harness/progress.md`；规格、合同、报告、错误与改进分别在同一 `docs/harness/` 下维护。`Tasks/index.json` 保持空任务表，不双写任务状态；根入口所说的 Tasks 接力只用于分支/执行者的上下文笔记，从 progress 链接，包含源修订、dirty 范围、证据指针、下一动作及验收，不复制进度状态。

验收通过后按 taskId 结束当前快照；不通过先记录报告，回滚只在已核定的当前任务范围内按授权执行，不能回滚别人的并行改动。Document 中的提交/发布仍须遵守用户授权，不因选模式而自动执行。

每完成三个迭代进行维护窗口：improver 分析架构/流程摩擦，doc-cleaner 核对文档一致性；同类错误累计三次、同任务连续两次失败或重大重构等按上游异常条件触发。所有角色把需返工/调试的问题追加到 error-log，维护结果回填 progress。没有变化时不批量重写文档。

上下文使用既有 `context.py`/context-index：按模块或路径定位，读直接依赖；恢复时复核分支与当前下一动作，源码、序列化、包、工具链或环境变化后只重核受影响结论。源码、接线、运行分别留证，不沿用旧执行结果冒充当前验收。
