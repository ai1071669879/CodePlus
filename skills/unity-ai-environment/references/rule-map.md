# 覆盖范围与适配边界

Unity 包自带完整通用底座，单独安装即可。行为正文由 rules.json 定位，字段统一由 configuration.md 定义；本页只作迁移核对。

| 通用职责 | 包内落点 | 适配重点 |
| --- | --- | --- |
| 平台入口与规则加载 | 权威规则、规则路由和薄入口 | 根/嵌套 Unity 根、新会话读取证据 |
| 身份/岗位与只读准备 | whoami/identity/clear-identity | 真实注册、自述差异、可信身份与本机缓存分开 |
| 路径/类型/职责授权 | policy + scope | 敏感/治理、资源文件授权、TA 代码附加范围、内容归属 |
| 原则、实现和协作 | project-rules.md | 查找复用、当前分支、完整切片合同及独立验证 |
| 交付与追踪 | 交付深度、验证风险、Tasks | 建档与等级分开；来源修订、人工认领/验收和历史 |
| 工程导航 | profile/context-index、context --query | 模块/API、Git 范围时效、运行可达需额外证据 |
| 生成与提交 | generated_paths、capabilities、conventions | 正式工具链及目标项目自己的提交语言/格式 |
| 意图契约与文档权威（intent） | rules.json → project-rules.md；task-contract.md、authority.md、golden/ | 项目自己的 Keep/Rewrite 边界、文档权威等级与失效日期、产物基准样例 |
| 执行节奏与交付回执（execution） | rules.json → project-rules.md；quality-workflows.md、contract_check.py、Tasks 模板 | 结构差异表、分步/延后门禁、编号回执与报告口径 |
| 本地/CI/服务端检查 | 管理工具 + CI 指引 | 可信策略/身份/变更集、保护机制及实际拒绝证据 |

## Unity 与策划覆盖

| 团队职责 | 完整规则 | 目标工程需接入 |
| --- | --- | --- |
| 生命周期/异步/资源/性能 | unity-rules.md | 基类、加载释放/池/更新/日志入口、实测场景 |
| 程序集/平台/网络与存档 | unity-rules.md | 宏、依赖、热更/生成机制、协议及兼容门禁 |
| UI、Prefab、美术与 TA | unity-rules.md + policy | 文件归属、控件绑定/正式导出、修改前提示、首版人工复核 |
| 版本文档预检/拆分/变更同步 | planning-workflows.md + Tasks | 来源修订、候选风险、各主负责人；保留认领及状态 |
| 配表分析/差异/正式导出检查 | planning-workflows.md | 独立源工程、格式/关联键、生成器及跨端同批输出 |
| 事件图分析/预览/编辑 | planning-workflows.md | 节点语义、实际编辑/保存/验证/导出入口及业务分支 |
| GC/CPU/内存/帧/Shader/未使用类型 | audit-capabilities.md | 每类的真实工具、输入、适用版本、证据与局限 |

九个预置能力槽位均从 unconfigured 开始。配表、事件图、UI 以及六类审计须登记真实工具后使用。配置分析/事件定位可先做只读上下文和差异预览；参数校验不代表已执行正式修改或导出。内存快照、Profiler 格式、专用类扫描器及编辑器集成没有伪装成随包解析器。

## 工具与检查边界

bootstrap 提供 plan/apply --diff、全树静态根发现、嵌套入口和整批冲突保护。checker 提供规则/入口/链接校验、项目 skill 清单、身份声明比对、候选范围约束、导航时效及任务修订/审批/验收检查。context 返回范围后用 rg 定向列文件；不全仓预读。项目 skill 发现只看目标 .codex/.claude 的一层 SKILL.md 目录，平台加载另测。

任务契约判定由随包 `contract_check.py` 的 check/baseline/selftest 提供：校验章节与机器块、禁止项正则、`[Rewrite]` 内的 public 类型和产物基准，退出码 0/1/2 分别表示通过/违规/用法错误或未验证。契约条款本身、真实基准样例和工程门禁仍须项目自备，判定器只读项目树，不执行构建、测试或生成器。

本机配置源/Unity 路径由操作者给出并人工维护；identity 只管理身份缓存。外部源工程独立核对规则、账号与授权。Tasks 正文由 agent 按实际操作回填，checker 不虚构人类认领/批准。工程命令、远端认证、聊天确认、AI 实际加载和服务器拦截均需另外实测；AI 审查只提供线索。

不移植源项目账号、模块/事件 ID、节点字段、菜单、资源管理器/日志类型、程序集分层、生成 C# 目录、配置格式或快照特殊签名。新工程的程序集制度由负责人制定；迁移已有工程时保留其禁改条款和实体/共享契约确认，不能用通用模板降低限制。角色与 code_paths 都不能跨越敏感职责。

## 去重与维护

不要同时叠装两套项目环境。共同底座在两个独立包内保留同步发行副本；项目内部规则正文、schema 说明、生成目录和能力状态各保持单一来源。公共脚本 bootstrap.py/check_env.py/contract_check.py、规则 project-rules.md、配置合同 configuration.md、任务模板 task-template.md/task-contract.md、文档权威 authority.md、产物基准 golden/README.md、安装与 CI 说明 setup-guide.md/ci-integration.md 及公共测试同步维护，Unity 差异只放专用资产和说明。

更新后运行两包测试、skill 校验和隔离初始化检查，再比较安装基线发布。Unity 包从包目录运行：

```text
python -X utf8 -B tests/test_unity_environment.py --skill .
```

已有权限、人工认领/验收、历史和更严格制度保留；只读预览后逐项合并，不删除后重装来绕过冲突。


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

U2–U4：unity_checks.py + unity-validation.json + unity-tooling.md，覆盖测试/性能/诊断/资源证据；U1 仅提供互斥适配指引和登记。运行 `python -X utf8 -B tests/test_unity_quality.py --skill .`。真实 Editor/Player、分析器、LFS/合并和设备结果仍分别验证。


## 核心摘要、基线与适配覆盖

根AGENTS直接保留四项原则、开始任务/身份范围/当前分支、生成物/敏感边界、协作、验证与交付；Unity补资源/meta、程序集/依赖、内容导出和设备验收。详细流程仍在原正文，只新增adaptation唯一规则来源。摘要不得替代原条款或重复定义权限。

bootstrap自动全树静态扫描→baseline.py生成文件/技术栈/已有规则/命令来源基线→证据适配profile/context/project-adaptation→entry_budget校验完整AGENTS→整批冲突预检后写入。源码/工程清单/配置/文档/CI/资源元数据覆盖，敏感/缓存/链接/大文本排除与缺口显式记录；不声称运行和全仓语义结论。保留原回归及新test_baseline.py/test_core_bootstrap.py/test_core_contract.py，公共实现和测试两包镜像。
