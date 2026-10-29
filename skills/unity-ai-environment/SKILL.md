---
name: unity-ai-environment
description: "Use when 初始化、迁移或维护 Unity 项目的 AI 工作环境，涉及程序/策划/美术/TA 职责、规则与权限、工程导航、配表/事件图流程、资源与性能验收或跨平台 AI 入口；普通游戏功能实现不触发。"
---

# Unity 项目 AI 环境管理

为 Unity 团队建立一套可维护的 AI 协作环境，覆盖开发、策划、资源与验证。原生模式自带通用底座、Unity 规则、策划流程、模板和 Python 3.10+ 工具；另可选择 unity-harness-init 模式，保留其 Unity Skills REST、Copilot /fleet 等强制依赖。版本、渲染管线、热更框架和配置格式均按目标工程核对。

## 初始化

1. 确认用户授权的仓库/工作区根和 Unity 工程根，读取已有规则与权限，记录分支、HEAD、未提交改动。先读 [配置步骤](references/setup-guide.md) 和 [Unity 发现与适配](references/unity-discovery.md)。不把 `Assets/` 所在目录直接当作整个仓库根。
2. 全面静态扫描工作区源码、配置、依赖、程序集清单、文档、CI、测试和资源元数据，建立项目基线。再核读 Editor/平台/渲染、生命周期、资源/日志、配置源/导出器、事件图、UI绑定等真实入口，形成带证据的项目适配规则。缓存明确排除；不启动导入、安装或猜菜单/API。
3. 使用随包完整模板预览；把结果中的 optional_tools、workflow_options 展示给使用者，说明名称、能力、前置、配置入口和互斥关系，再按其选择初始化。官方 CLI 沿用 unity-editor-cli，Coplay 沿用 unity-editor-mcp，AnkleBreaker 为 unity-editor-anklebreaker，不建重复槽位。`<skill-dir>` 是本 SKILL.md 的目录；平台可多选或使用 all。

   ```text
   python <skill-dir>/scripts/bootstrap.py plan --project <workspace-root> --project-name <name> --platform codex --diff
   python <skill-dir>/scripts/bootstrap.py apply --project <workspace-root> --project-name <name> --platform codex --workflow native --tools <已选能力ID或none>
   ```

   默认原生模式、外部工具关闭；已有工程省略 workflow 时保留原模式。选择 `--workflow unity-harness-init` 时自动登记其必需依赖并替换冲突正文，缺依赖不回退原生模式。模式对比见 [工作流整合](references/workflow-integration.md)，工具配方见 [Unity 工具](assets/project/Docs/ai/unity-tooling.md)。模式切换先预览、合并状态与宿主入口，冲突整批不写；选择配置不等于安装或 verified。

   脚本全面静态扫描目标工作区，识别任意深度的 Unity 根并读取 ProjectVersion；多个根时用 `--unity-root <relative-path>` 明确选择。根在子目录时，会生成该目录对应的薄入口。已有入口文字保留，任何配置冲突整体退出 2，不覆盖或删除后重装。
4. 按 [配置合同](assets/project/Docs/ai/configuration.md) 填 profile、context-index 和真实能力入口。由获授权维护者登记用户、角色路径、文件类型、内容归属和代码附加范围；所有默认授权为空。自述岗位不能赋权；迁移时保留已有的实体/共享契约确认与更严格的程序集制度。配置源工程独立核对授权，个人路径只记在被忽略的 `.ai-local/unity.json`。
   原生模式的重构类项目意图契约、文档权威登记与产物基准随包部署：`Docs/ai/task-contract.md`、`Docs/ai/authority.md`、`Docs/ai/golden/`、`tools/ai/contract_check.py`。包内的 `public-type-baseline.txt` 只有说明头，初始化后由维护者运行 `python tools/ai/contract_check.py baseline --paths <程序集或模块根> --out Docs/ai/public-type-baseline.txt` 生成真实清单；不覆盖项目已有契约与基准。
5. 运行管理检查与身份查询，并由已登记成员缓存本人账号：

   ```text
   python tools/ai/check_env.py check
   python tools/ai/project_setup.py list
   python tools/ai/project_setup.py check
   python tools/ai/check_env.py whoami --user <registered-user> --role <declared-role>
   python tools/ai/check_env.py identity --user <registered-user> --role <declared-role>
   ```

6. 使用真实工程工具分别验证编译、目标玩法、资源导入、Player/设备和必要的性能/跨端兼容；初始化检查不会替代或自动运行它们。所选 AI 平台开新会话验证实际加载，CI/服务端机制按 [CI 接入](references/ci-integration.md) 单独配置与实测。

## 核心入口、全面扫描与适配

根 AGENTS.md 在 500 token 内直接保留原则、开始任务、身份/路径与敏感边界、协作和交付要求；Unity 版另保留资源/程序集/生成物/设备验收边界。详细流程仍按 rules.json 唯一维护，摘要不增加第二套规则定义。使用包内完整核心模板，保留分段和可执行步骤，不在安装后再手写一份更短摘要。生成时同时检查根核心完整性和包含人工旧文/标记的全文预算；不满足则整批报告冲突，保留原文。项目路径适配与重新核计按配置合同执行。

plan/apply 自动扫描整个授权项目树（不是仅预读少量目录），生成 `Docs/ai/project-baseline.json` 与 `Docs/ai/project-adaptation.md`，并以可证事实适配 profile/context。盘点含覆盖率、文件摘要、Git基点、技术栈、模块、已有规则、声明的门禁及证据、待确认项。AI 还须核读关键来源和冲突，再完成目标项目的适配；静态检测不能替代语义判断。扫描不会给账号赋权，不把候选/声明命令写成已执行。

原生模式下，需要操作**已经打开**的 Editor（刷新导入、调用受权静态 Editor 方法、批处理测试、Player/日志取证）时，用随包可选 gate：`Editor/UnityEditorGate/UnityEditorGate.cs` + `tools/ai/unity_editor.py`。它只按 `Library/EditorInstance.json` 的 PID 定位，不自动启动/杀死 Editor，同 id 不覆盖证据；协议、失败模式与授权边界见 [Unity 编辑器自动化](references/unity-editor-automation.md)。不启用时删除 `Editor/UnityEditorGate/` 即可，不影响其他检查器。

二进制只记元数据；内置规则识别的凭据/本机配置、缓存和外部链接不读取内容（未识别形态须显式排除），超大文本/不可读文件明确报告缺口；不称为全仓语义或运行审查。初始化后的日常任务按导航定向读取，不反复全扫。详细字段、500 token 口径和升级方式见 [配置合同](assets/project/Docs/ai/configuration.md)。

## 项目中安装的完整规则

| 文件 | 内容 |
| --- | --- |
| `Docs/ai/project-rules.md` | 通用任务、身份、范围、实现、协作与交付原则 |
| `Docs/ai/unity-rules.md` | 生命周期/异步、资源/序列化、性能、程序集/平台、网络/存档、UI 与角色边界 |
| `Docs/ai/planning-workflows.md` | 策划版本预检/拆分/同步、配置源定位/预览/正式导出、事件图与业务验收 |
| `Docs/ai/audit-capabilities.md` | GC、CPU、内存快照、Profiler 帧、Shader 构建日志与未使用类型审计的输入/证据/限制 |
| `Docs/ai/rules.json` + `configuration.md` | 唯一规则来源和配置字段合同 |
| `Docs/ai/task-contract.md` + `authority.md` + `golden/` | 意图契约模板、文档权威登记与失效日期、产物基准 |
| profile/policy/context/task 模板 | 项目事实、最小授权、能力导航和跨会话追踪 |
| `Docs/ai/workflow.json` + `workflow.md` | 当前模式、唯一状态来源与执行流程 |
| `Docs/ai/setup-options.json` + `tools/ai/project_setup.py` | 工具/模式选择目录与前置检查 |
| `tools/ai/context.py` | 按多个模块或路径定向选择既有导航 |
| `tools/ai/check_env.py` | 规则路由、身份冲突、类型/路径、导航时效、任务修订和验收检查 |
| `tools/ai/contract_check.py` | 契约机器块、禁止项、新增 public 类型与产物基准的判定 |

能力状态只在 profile.capabilities 维护，unity.config_source/event_tools/ui_binding 引用其 ID。没有工具时保持 unconfigured，仍可完成规则、权限和导航准备。六类审计同样须接入目标工具，包内没有伪造的快照/Profiler 解析器。AI 只做可追溯的分析和差异预览，不直接修补生成 C#、导出文件或序列化图来伪装完成。

原生模式中，重构、重建或替换既有设计的任务必须生成并维护 `Docs/ai/task-contract.md`、`Docs/ai/authority.md` 与 `Docs/ai/golden/`，单任务契约存 `Tasks/<task>-contract.md`。收口前运行 `python tools/ai/contract_check.py check --contract Tasks/<task>-contract.md`，退出码 0 才进入工程门禁；`python tools/ai/contract_check.py selftest` 在临时目录自检判定器，不写项目目录。契约通过不替代 C# 编译、Editor/Player 运行与资源/性能验收。

## 已包含的质量与工具环境

C1–C5 已随初始化部署：[行为评测与架构约束](assets/project/Docs/ai/quality-workflows.md)、[工具信任/环境自检/脱敏扫描](assets/project/Docs/ai/tool-integrations.md)。在目标根先运行 `python tools/ai/environment.py doctor` 和 `python tools/ai/evaluate.py validate`。依赖图和真实轨迹由项目工具提供，未配置的必需门禁不能记为通过。

C6 Serena、C7 Context7、C8 OpenSpec 为按需接入，全部复用 profile.capabilities，不另建工具/任务状态表。先核来源、固定版本、许可和数据边界；本包不安装第三方软件、不自动上传项目或执行任意接入命令。完整用法已在上述随包文档，无需另找模板。

U2–U4 已提供 [Unity 验收工具与合同](assets/project/Docs/ai/unity-tooling.md)：NUnit XML、归一化性能预算、分析器 SARIF、选定 Assets 的 meta/GUID。`unity_checks.py` 不自动运行 Editor；U1 官方 CLI/Coplay MCP/AnkleBreaker MCP 按需互斥选择；Harness 模式使用强制 Unity Skills REST 通道，保持工程既有程序集与依赖制度。

## 日常管理与交付

开始先读目标工程的 workflow.json/workflow.md，按选中模式执行。`project_setup.py list/check` 列配置与前置；`context.py --query/--paths` 复用现有索引定向导航。原生模式 `check`、`whoami`、`clear-identity`、`context --query`、`scope --user --paths` 从项目根运行；详见配置合同。原生模式重构任务的契约判定用 `python tools/ai/contract_check.py check --contract Tasks/<task>-contract.md`，判定器自检用 `python tools/ai/contract_check.py selftest`。原生模式需要操作**已打开**的 Editor 时用可选 `tools/ai/unity_editor.py`（协议与授权边界见 [Unity 编辑器自动化](references/unity-editor-automation.md)）。岗位声明冲突保持只读；导航 stale/unknown 复核真实入口。原生模式的版本级、多人或跨会话工作进入 Tasks；Harness 状态唯一在 docs/harness/progress.md，Tasks 只保留分支/执行者接力，单点修改按实际追踪需要处理。任务候选不被未确认文档机械阻断，完成时核对负责人及验收证据。

交付生成/冲突清单、工程根和版本的证据、身份范围、能力已接入/未接入状态、命令和退出码。区分环境静态检查、C# 编译、Editor、Player/设备、服务端与性能证据；缺项明确保留。维护既有工程时先比较差异并合并，不强行改目录、渲染/网络架构、程序集或生成器。

交付前回读目标项目的实际 AGENTS.md，确认 `check` 的根入口报告 `core_matches=true` 且预算通过；预览或模板截图不能代替实际落盘结果。

常见误区：把现有项目的资源管理器、Logger、配置 ID、工具菜单和热更方案当通用前提；把 Planner/TA 的目录权限当程序授权；把 Editor 采样或编译通过当目标设备验收。用真实能力登记、文件职责复核和分层验证纠正。
