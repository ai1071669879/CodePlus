# 覆盖范围与适配边界

本页用于初始化和迁移的覆盖核对。行为以项目 rules.json 指向的正文为准，字段只由 configuration.md 定义；这里不建立第二套规则。

| 团队职责 | 包内落点 | 目标项目必须确认 |
| --- | --- | --- |
| 多平台统一与核心文件加载 | 权威规则、规则路由表、各平台薄入口 | 实际使用平台及新会话加载证据 |
| 身份初始化、岗位差异和只读准备 | whoami/identity/clear-identity | 注册账号、可信身份来源、维护者 |
| 最小授权、敏感和治理职责 | policy + scope | 普通/附加/禁止路径、类型、代码范围和内容归属 |
| 自述岗位、跨职责/共享契约确认 | 缓存岗位比对、change_controls、任务记录 | 已登记职责和项目特有的确认范围 |
| 四项开发原则及查找复用 | project-rules.md | 已有类型/API、真实调用和兼容门禁 |
| 交付深度与验证风险 | 轻量/标准/专项交付，另行判断四档验证风险 | 按实际影响选门禁；建档另按追踪需要决定 |
| 工程地图和能力导航 | profile/context-index、context --query | 根、别名、真实入口、修订和适用限制 |
| 任务追踪、修订变化与多人验收 | Tasks 索引、Markdown 模板、check | 来源修订、主动认领、保留历史、负责人的验收证据 |
| 生成文件与正式工具 | profile.generated_paths、capabilities | 源→正式工具→同批产物→验证链 |
| 提交和分支管理 | 项目提交约定、当前分支原则 | 既有语言/格式；切换/整合的明确指令 |
| 协作分工与独立验证 | 负责人决策、完整切片合同、按风险复验 | 可用工具和团队职责；不绑定模型或配额 |
| 意图契约与文档权威（intent） | rules.json → project-rules.md；task-contract.md、authority.md、golden/ | 项目自己的 Keep/Rewrite 边界、文档权威等级与失效日期、产物基准样例 |
| 执行节奏与交付回执（execution） | rules.json → project-rules.md；quality-workflows.md、contract_check.py、Tasks 模板 | 结构差异表、分步/延后门禁、编号回执与报告口径 |
| 本地、CI、服务端和 AI 审查 | check/scope + CI 指引 | 可信身份/策略/变更集、保护机制和实际触发证据 |

## 工具覆盖与边界

| 操作 | 随包实现 | 需要接入的部分 |
| --- | --- | --- |
| 初始化与更新预览 | bootstrap plan/apply --diff、整批冲突预检、幂等和入口保留 | 人工比较/合并既有制度，不自动清空授权 |
| 管理配置检查 | 结构、规则唯一来源、入口/链接、能力证据 | 模型实际读取及项目业务语义 |
| 身份和候选路径检查 | 岗位冲突、类型/路径/归属约束、清缓存 | 远端认证、文件系统隔离、聊天确认的真实性 |
| 工程导航 | 条目查询、Git 范围修订变化检查 | 在命中目录用 rg 定向列文件，核验调用/平台/注册 |
| 项目 skill 清单 | 只发现目标 .codex/.claude 的一层 SKILL.md 目录 | 用户级/平台其他目录由操作者清点，实际加载另测 |
| 任务管理 | 元数据、依赖循环、来源修订、所需审批及完成证据检查 | agent 按需求更新 Markdown；不自造人类认领/验收 |
| 工程门禁 | 登记真实 build/test/lint 参数数组 | 编译/测试/运行/性能工具不由 checker 自动执行 |
| 任务契约判定 | contract_check.py check/baseline/selftest（禁止项、新增 public 类型、产物基准） | 契约内容本身、真实基准样例；不替代工程门禁 |
| CI/钩子/自动审查 | 平台无关接入指引 | 无预装钩子或伪装服务器拦截；AI 审查只是线索 |

不移植源团队账号、业务目录、专用 API、托管地址、个人路径、模型或资源预算。通用包不包含游戏策划流程。自然语言入口只作意图路由，不需要另造关键词服务。

## 去重与后续维护

单个项目只选择一套环境包；Unity 包已经包含通用底座，无需叠装。两包独立可分发，因此共同脚本和通用规则保留同步副本；包内同一规则正文、字段语义、生成目录和能力状态各有唯一来源。

更新公共实现时，同步两包的 bootstrap.py、check_env.py、project-rules.md、configuration.md、task-template.md、task-contract.md、authority.md、golden/README.md、contract_check.py、setup-guide.md、ci-integration.md 和公共测试。Unity 差异只放项目资产、能力与专用说明，避免分叉公共算法。运行两包各自测试入口和 skill 校验器，再在隔离目录做 plan→apply→check；比较已安装文件基线后发布。测试入口从包目录运行：

```text
python -X utf8 -B tests/test_review.py --skill .
```

迁移以当前代码、测试、既有决定和登记授权为依据；保留比模板更严格的约束和已有状态，不从“模板允许”推导“旧项目已授权”。


## 已批准扩展覆盖

| 编号 | 随包落点 | 必须另行取得的证据 |
| --- | --- | --- |
| C1 | evaluate.py、evals.json、quality-workflows | 真实会话轨迹、动作归一化来源与产物 |
| C2 | quality.py architecture、architecture-policy | 目标语言依赖抽取、完整性与修订 |
| C3 | profile.integration、tool-integrations、Inspector 接入步骤 | 固定可信工具、握手和最小只读调用 |
| C4 | environment.py doctor/modules、本机映射 | 所需版本、实际可执行文件和环境兼容 |
| C5 | quality.py secrets、gitleaks.toml | 固定 Gitleaks 安装和明确扫描范围 |
| C6–C8 按需 | Serena/Context7/OpenSpec 的能力登记与接入说明 | 授权、来源/许可、版本和实际功能；复用导航/Tasks |

不捆绑第三方实现，不自动安装，不强制 Docker、特定模型或托管平台。外部服务返回不具有治理权限。公共代码还须同步 environment.py、quality.py、evaluate.py、新公共模板和三组升级测试；初始化/管理原回归仍保留。

新增门禁从各包根运行：

```text
python -X utf8 -B tests/test_bundle_upgrade.py --skill .
python -X utf8 -B tests/test_upgrade_tools.py --skill .
python -X utf8 -B tests/test_evaluations.py --skill .
```


## 核心摘要、基线与适配覆盖

根AGENTS直接保留四项原则、开始任务/身份范围/当前分支、生成物/敏感边界、协作、验证与交付；Unity补资源/meta、程序集/依赖、内容导出和设备验收。详细流程仍在原正文，只新增adaptation唯一规则来源。摘要不得替代原条款或重复定义权限。

bootstrap自动全树静态扫描→baseline.py生成文件/技术栈/已有规则/命令来源基线→证据适配profile/context/project-adaptation→entry_budget校验完整AGENTS→整批冲突预检后写入。源码/工程清单/配置/文档/CI/资源元数据覆盖，敏感/缓存/链接/大文本排除与缺口显式记录；不声称运行和全仓语义结论。保留原回归及新test_baseline.py/test_core_bootstrap.py/test_core_contract.py，公共实现和测试两包镜像。
