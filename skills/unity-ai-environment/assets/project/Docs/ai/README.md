# 项目 AI 环境入口

| 文件 | 职责 |
| --- | --- |
| [project-rules.md](project-rules.md) | 任务行为与唯一规则定义 |
| [rules.json](rules.json) | 规则ID到权威正文的路由 |
| [task-contract.md](task-contract.md) | 意图契约模板与判定口径（重构类任务必附） |
| [authority.md](authority.md) | 文档权威等级、已失效条款与待复核条款 |
| [golden/README.md](golden/README.md) | 产物基准的登记与比较规则 |
| [configuration.md](configuration.md) | 配置字段与管理命令的唯一说明 |
| [project-profile.json](project-profile.json) | 项目事实、门禁命令、生成物与能力 |
| [access-policy.json](access-policy.json) | 账号、角色、路径、类型与内容归属 |
| [context-index.json](context-index.json) | 模块导航与核验修订 |
| [task-template.md](task-template.md) | 任务正文模板 |
| [unity-rules.md](unity-rules.md) | Unity工程职责与分层验收 |
| [planning-workflows.md](planning-workflows.md) | 策划版本、配置与事件图流程 |
| [audit-capabilities.md](audit-capabilities.md) | 六类专项审计输入、证据与接入合同 |
| [../../Tasks/index.json](../../Tasks/index.json) | 任务元数据 |
| [../../tools/ai/check_env.py](../../tools/ai/check_env.py) | 环境管理CLI |
| [../../tools/ai/contract_check.py](../../tools/ai/contract_check.py) | 契约机器块、禁止项、新增类型与产物基准的判定 |

每项任务加载本入口、project-rules、profile、policy与命中的导航；配置协议按 configuration.md，规则正文按 rules.json 保持唯一。初始账号、角色路径与工程命令为空，不能据此推断写入授权或工程验证通过。

先核身份、自述/登记岗位、分支/HEAD/已有改动，再按任务定位少量真实入口与复用机制。原有更严格的规则保留；不能用新模板静默放宽。

**重构、重建或替换既有设计的任务，先写 [意图契约](task-contract.md)（`Tasks/<task>-contract.md`）再动手**：契约点名 `[Keep]`/`[Rewrite]`/`[Forbidden]`/`[Superseded]`，在其范围内优先于本入口与 project-rules 的通用条款；引用文档前按 [权威登记](authority.md) 判定等级。契约机器块由 contract_check.py 判定，退出码 0 才进入工程门禁。

常用命令（项目根执行）：

```text
python tools/ai/check_env.py check
python tools/ai/check_env.py whoami
python tools/ai/check_env.py context --query <keyword>
python tools/ai/check_env.py scope --user <registered-user> --paths <relative-path> ...
python tools/ai/contract_check.py check --contract Tasks/<task>-contract.md
python tools/ai/contract_check.py selftest
```

文件发现、静态检查、平台实际加载、工程编译/运行及服务器强制检查分别保留证据；check 不执行构建或自动调用能力工具。


扩展工具（仍在项目根执行）：

```text
python tools/ai/environment.py modules
python tools/ai/environment.py doctor
python tools/ai/evaluate.py validate
```

| 内容 | 实现与输入 |
| --- | --- |
| [工具接入规则](tool-integrations.md) | [environment.py](../../tools/ai/environment.py)，C3/C4 信任清单、版本探测，C6–C8 按需模块 |
| [质量证据](quality-workflows.md) | [evaluate.py](../../tools/ai/evaluate.py)、[evals.json](evals.json)，C1 行为用例与轨迹评分 |
| 架构约束 C2 | [quality.py](../../tools/ai/quality.py) + [architecture-policy.json](architecture-policy.json)，需实际依赖图 |
| 本地扫描 C5 | 同一 quality.py + [gitleaks.toml](gitleaks.toml)，需自行接入可信 Gitleaks |

外部接入默认 disabled/unconfigured；内置工具与模板已经部署。环境结构、版本探测、日志证据与真实模型/工程执行分别报告，不能互相替代。

Unity 测试 XML、性能预算、SARIF 和显式 Assets 检查：见 [Unity 工具与验收](unity-tooling.md)、[unity_checks.py](../../tools/ai/unity_checks.py) 与 [unity-validation.json](unity-validation.json)。U1 编辑器接入按需互斥选择，不自动启动或安装。


## 项目基线与适配

初始化的 plan/apply 会全面静态盘点目标项目并生成 `Docs/ai/project-baseline.json`（机器可核对的文件/技术栈/证据基线）和 `Docs/ai/project-adaptation.md`（启动时必读的适配规则、已有制度入口和待确认项）。账号授权继续只在 access-policy，事实/能力继续在 profile，导航继续在 context-index；扫描不复制第二份权限表。详细字段见 [configuration.md](configuration.md)。

```text
python tools/ai/baseline.py scan
python tools/ai/baseline.py compare
```

scan 只读输出新观察；compare 只读比较已保存基线与当前工程。源码新增/删除/内容变化分别报告；缓存、凭据、本机数据和受管输出的排除项也要可查。静态基线不证明编译、运行、性能或业务语义。普通任务不要求重复全面扫描；门禁/profile/adaptation变化时由获授权维护者更新，保留历史及既有更严格规则。

AGENTS 是核心决策摘要，详细规则只在 rules.json 登记的来源维护；不得另复制完整正文导致分叉。预算由 [entry-budget.json](entry-budget.json) 与 `tools/ai/entry_budget.py` 核对，完整文件含人工文字和区块标记均计入。预算冲突先保留原文并报告，不通过删除旧规则解决。
