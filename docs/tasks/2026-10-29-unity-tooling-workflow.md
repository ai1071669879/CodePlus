# Unity 可选工具与工作流整合任务

状态：已完成配置与工作流整合，独立门禁通过，live 与仓库已同步。用户于 2026-10-29 授权将三种 Unity 连接工具纳入可选配置，并从指定两个工作流提炼适合既有机制的内容；随后明确要求 Harness 作为可选模式保留其强制依赖，在选中时屏蔽冲突的原流程。未授权在本机安装这些第三方工具、连接真实 Unity、提交或发布。

## 意图契约

本契约在点名范围内优先于复用优先等通用约定，不超越凭据边界、提交权限和验证等级。

- [Keep] `profile.capabilities` 是能力状态唯一来源；`context-index.json` 是导航来源。原生模式保留 `Tasks/index.json` 任务状态；Harness 模式采用上游 `docs/harness/progress.md`，`Tasks` 只保存接力记录，不维护第二份任务状态。保留既有 ID、用户权限、整批冲突不写、500 token 入口证书、Editor/Player/性能证据分层和所有工作区已有改动。
- [Rewrite] 仅本机 `unity-ai-environment` 的可选工具发现/配置与相关 Unity 工作流扩展。源头为 `C:/Users/Administrator/.codex/skills/unity-ai-environment/`，验证后使用既有同步工具镜像到仓库。具体文件在调研完成后的结构表中锁定。
- [Forbidden] 同一模式不维护第二个任务状态表、第二个能力状态表；不自动下载执行第三方工具；不写真实账号/凭据；不改变全局规则、配置或另一个项目技能；不覆盖已有受管定制。只允许既有同步工具纠正已由只读预览确认的指南生成日期，正文必须保持一致。检查使用源码 diff、限定关键字搜索、行为回归和同步前后哈希。
- [Superseded] 2026-10-29：前一调研方案“去掉 Harness 的 Unity Skills 强制依赖”被用户明确否决。Harness 模式保留 Unity Skills REST、Copilot CLI /fleet、自包含 track、文件分区、TDD、不同模型系列的独立 Reviewer 与维护窗口。`rule-map.md` 关于所有公共文件必须两包相同的条款，在本次 Unity 专有 bootstrap 扩展范围内由本契约替代；通用项目包保持原状。

## 调研网络范围

只读获取公开上游文档、源码、版本/许可元数据。允许目标域名：github.com、raw.githubusercontent.com、api.github.com、docs.unity.com、unity.com、activation.unity3d.com、coplaydev.github.io、www.npmjs.com、registry.npmjs.org、unpkg.com。允许命令请求上述域名并将公开文本/归档保存在隔离的本机临时目录；不执行下载脚本，不安装依赖，不上传本地工程、私有内容或凭据。其他搜索仅用公开网页搜索工具。

## Shape First（调研后锁定）

1. 核心概念：可选工具说明、使用者选择、配置候选与验证证据；任务上下文、增量交付与接力。
2. 复用：`scripts/bootstrap.py:run(args)` 的模板事务；`tools/ai/environment.py:modules(profile)` / `doctor(root, profile, probe=False, capability_id=None)`；`check_env.validate_profile` / `validate_context` / `validate_tasks`；`baseline.scan_project` / `adapt_project`；现有任务正文和契约模板。
3. 可读实现：`project_setup.py` 负责无执行副作用的工具/模式选择与前置检查；`context.py` 负责从既有索引定向找路线；`workflow.md` 负责当前模式的工作流程。Harness 专用覆盖资产只在选中模式时替换冲突正文，原生模式不加载该覆盖。新增 JSON 目录只存说明，不存能力状态。

## 结构差异表（实施范围）

| 行 | 动作与文件 | 责任及为何需要 | 模块 |
| --- | --- | --- | --- |
| 1 | 新增 `assets/project/Docs/ai/setup-options.json`、`workflow.json`、`workflow.md`；修改 profile | 静态选择目录与唯一模式配置；既有 profile 仍保存所有能力状态 | Unity skill |
| 2 | 新增 `assets/project/tools/ai/project_setup.py`、`tests/test_setup_options.py` | 复用 profile 校验，列工具、选择预览、必需依赖检查；现有 doctor 只检查已登记工具，不处理初始化选项 | Unity skill |
| 3 | 修改 `scripts/bootstrap.py` | 在原整批事务中加入 `--tools`/`--workflow` 和条件覆盖；拒绝双初始化入口或静默安装 | Unity skill |
| 4 | 新增 `assets/project/tools/ai/context.py`、`tests/test_context_routes.py` | 复用原 context-index/Git 时效；增加按路径和多模块定向查询，不复制索引或全仓读取 | Unity skill |
| 5 | 新增 `assets/workflows/unity-harness/` 下模式覆盖；新增 `references/workflow-integration.md` | 选中时实际替换冲突流程与模板；保留上游必需前置，不叠加两套执行方法 | Unity skill |
| 6 | 修改 SKILL、setup-guide、rule-map、unity-discovery、README、rules.json、configuration、tool-integrations、unity-tooling、task-template | 串联目录、配置配方、模式权威与接力；复用既有身份/授权/证据规则 | Unity skill |
| 7 | 通过 sync-config 更新指南生成日期 | 本机 check-consistency 发现既有日期 2026-10-26 早于 live 2026-10-28；预览确认唯一变化为生成日期、所有正文/快照一致 | 仓库生成元数据 |

采用/排除：工具的版本/数量不写成固定能力承诺，实际 tools/list 为准；正常模式吸收完整职责切片、文件归属与接力；Harness 模式保留发布包 0.1.4 的主流程和强制依赖，不在本机执行 npm CLI，不盲目导入其与当前权限冲突的自动覆盖/回滚；workflow-kit 吸收定向路由和分支/执行者接力，拒绝重复导航/状态表和覆盖受保护文件的 Git hooks。

每行验收：行为测试验证候选无副作用、默认关闭、选择与模式前置、冲突整批不写、路径导航范围、未知/越界拒绝；独立验证复跑全套 skill 测试和两种模式的隔离初始化。原生 Tasks 与 Harness progress 不得同时声明状态权威。实际第三方安装/Unity/MCP/模型宿主能力验证属于目标项目后续配置，不虚报通过。

## 计划与门禁

- [x] 对比上游与现有机制，锁定结构差异表及采用/排除原因。
- [x] 新行为先编写测试并记录旧实现失败；在隔离副本实施，发布仍须先写 live 源头。
- [x] 可选工具清单、选择和配置预览已实现；对应行为测试通过。
- [x] 导航/增量交付/接力与模式隔离已整合，局部门禁通过；完整独立回归已通过。
- [x] 独立验证前后核对源码/测试/配置哈希；已修复损坏配置的结构化错误处理。
- [x] live -> 仓库同步；相对链接、技能校验、树哈希与本机一致性通过。原有指南日期差异仅由同步工具修正，已核对正文无其它变化。

任何测试通过均不等于真实 Unity、MCP 握手或平台加载验收。本任务不运行这些集成。

## 当前证据与待关闭项

- `python -B -X utf8 tests/test_setup_options.py --skill .`：实现代理记录 RED（模块不存在及语义反例），最后 GREEN 20 tests，exit 0。changed_files 仅一个源码模块与其测试；已计数。
- `python -B -X utf8 tests/test_context_routes.py --skill .`：实现代理记录 RED（文件不存在及无-B启动写字节码），最后 GREEN 14 tests，exit 0，无跳过；目录联接逃逸实际覆盖。changed_files 仅同一个源码模块与其测试；已计数。
- `python -B -X utf8 tests/test_workflow_modes.py --skill .`：主线程先记录旧初始化不支持参数/无目录输出，补充 Windows 大小写反例后 GREEN 9 tests，exit 0。
- `test_core_bootstrap.py` 9 tests、`test_core_contract.py` 6 tests，均 exit 0；技能 quick_validate 输出 `Skill is valid!`，exit 0。
- 本次涉及模式/外部工具接口与规则权威，整体按 High 验证；独立 verifier 的前置摘要覆盖候选全体 78 文件。验证中发现既有配置 JSON 类型错误会触发 traceback，待独立报告后补负例、修复与重验，不将当前交付关闭。

第一轮 verifier：`status: failed`；既有/新增 15 脚本共 240 测试全部通过，但额外损坏输入场景复现两类 traceback。源码摘要前后均 78 文件，added/removed/modified 均空；源码未被验证者改动。3.10 AST、114 本地链接、两模式各 17 个唯一规则 ID 和技能校验通过。

修复片：`status: passed`，changed_files 仅 bootstrap.py 与 test_workflow_modes.py；先新增负例看到 14 个子场景失败，再加读取前类型/模式 guard。模式套件现 11 tests，core_bootstrap 9 tests，均 exit0；未扩大顶层异常吞并。第二轮独立验证前重新保存 78 文件摘要，与第一轮相比仅这两个已授权文件不同。

另一个导航补改提议因主线程错误前提撤回：验证命令实际输出 `commands.lint must be an argument list with a nonempty executable`，证明省略 lint 并非合法 profile；保持已通过的导航实现与测试，不为假设改 schema。该 `blocked` 已按错误前提解决，不是遗留缺陷。

第二轮独立验证：`status: passed`；15 脚本 242 测试全部 exit0，14 个损坏输入 plan/apply 场景全部结构化 exit2、无 traceback、零写入；两模式各 17 个规则 ID 无重复/错路由；3.10 AST/文档相对链接/技能校验通过。`V2_BASELINE 78 AFTER 78 ADDED [] REMOVED [] MODIFIED []`。真实 Unity/REST/MCP/Copilot/性能未执行，按配置工作范围排除，不宣称运行集成通过。

## 委派校准

| 工作 | 观察 | 结论与下次修正 |
| --- | --- | --- |
| explorer 广泛扩展点盘点 | 首轮输出被截断并包含错误的 Tasks 起始路径，未提供可用完整证据；缩为两个明确问题后取得事实 | 初轮是损失；限定问题和每段输出比扩大扫描更有效 |
| 两个独立 helper + 行为测试 | 两个代理分别负责选择/前置与导航，文件不重叠，按固定接口实现；主线程只整合初始化/模式与文档 | 并行执行有收益；依赖语义和输出格式必须在 brief 明确，补充后无需重构 |

## 最终交付与门禁

- 满足 Keep：原能力 ID、权限、根入口证书与扫描/冲突机制保留；能力/模式/当前模式状态来源明确。
- 满足 Rewrite：可选目录、配置流程、路径导航与两种互斥流程装配完成。
- 满足 Forbidden：未安装外部工具、未连接真实 Unity/REST/MCP/Copilot、未变更全局规则或通用项目技能、未创建交付提交。
- 满足 Superseded：Harness 强制依赖已保留，替代被否决的“移除依赖”方案；选中后原生冲突正文实际替换。

`powershell -NoProfile -ExecutionPolicy Bypass -File tools/sync-skills.ps1 -Only unity-ai-environment`：exit0，`mirrored (78 files)`。

`powershell -NoProfile -ExecutionPolicy Bypass -File tools/sync-config.ps1`：exit0；生成日期由2026-10-26更新为2026-10-29，所有规则正文/模板/快照已一致。与任务前保存副本逐行比较，唯一内容变化是版本日期。未修改live全局配置。

`powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify-repo.ps1`：exit0，八组全部PASS，决定性输出“全部通过：本机 live 环境与仓库快照一致（全局环境 + 项目技能）”。

`python -B -X utf8 tools/check-consistency.py`：exit0，19条规则及附加检查通过，决定性输出“结论: 全部一致”。

主线程在发布后比较所有78个文件SHA-256：live == 仓库 == 独立验证候选。源代码、测试、配置和文档均相同；现有工作区改动保留。

独立验证报告保留结构：

```text
status: passed
changed_files: []  # 验证未修改源；只有隔离夹具与报告
reused: none — read-only verification
evidence: 见下方逐项门禁；另有14个损坏输入场景均结构化exit2、零写入，两模式各17个规则ID无重复/错路由
assumptions: 真实Editor/REST/MCP/Copilot与性能未运行；这是配置交付范围外的目标工程验证
blockers: none
```

以下在隔离技能根逐一执行，表中给出可从同步后的技能根重放的命令；每项原始绝对路径argv、退出码与决定性输出已保存在本次验证日志。

| 命令 | exit | 决定性输出 |
| --- | --- | --- |
| `python -B -X utf8 tests/test_baseline.py --skill .` | 0 | Ran 13 tests in 0.537s; OK |
| `python -B -X utf8 tests/test_bundle_upgrade.py --skill .` | 0 | Ran 5 tests in 2.713s; OK |
| `python -B -X utf8 tests/test_context_routes.py --skill .` | 0 | Ran 14 tests in 6.808s; OK |
| `python -B -X utf8 tests/test_core_bootstrap.py --skill .` | 0 | Ran 9 tests in 3.056s; OK |
| `python -B -X utf8 tests/test_core_contract.py --skill .` | 0 | Ran 6 tests in 2.613s; OK |
| `python -B -X utf8 tests/test_entry_integrity.py --skill .` | 0 | Ran 7 tests in 1.740s; OK |
| `python -B -X utf8 tests/test_environment.py --skill .` | 0 | Ran 15 tests in 6.851s; OK |
| `python -B -X utf8 tests/test_evaluations.py --skill .` | 0 | Ran 15 tests in 9.922s; OK |
| `python -B -X utf8 tests/test_review.py --skill .` | 0 | Ran 36 tests in 17.150s; OK |
| `python -B -X utf8 tests/test_setup_options.py --skill .` | 0 | Ran 20 tests in 3.495s; OK |
| `python -B -X utf8 tests/test_unity_editor.py --skill .` | 0 | Ran 9 tests in 6.979s; OK |
| `python -B -X utf8 tests/test_unity_environment.py --skill .` | 0 | Ran 41 tests in 19.250s; OK |
| `python -B -X utf8 tests/test_unity_quality.py --skill .` | 0 | Ran 23 tests in 14.487s; OK |
| `python -B -X utf8 tests/test_upgrade_tools.py --skill .` | 0 | Ran 18 tests in 10.768s; OK |
| `python -B -X utf8 tests/test_workflow_modes.py --skill .` | 0 | Ran 11 tests in 6.104s; OK |
