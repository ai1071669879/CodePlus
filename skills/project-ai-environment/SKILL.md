---
name: project-ai-environment
description: "Use when 初始化、迁移、收敛或维护任意项目的 AI 工作环境，涉及团队规则、AGENTS.md、身份和路径权限、跨平台入口、工程导航、任务追踪或 CI 检查；普通功能开发不触发。"
---

# 通用项目 AI 环境管理

把项目规则、事实、职责和验证方式配置为可执行的协作环境。本包完整自包含，使用 Python 3.10+ 标准库；不需要原始项目、其他 skill、特定模型或 Git 托管服务。

## 先确定范围

- 初始化：为指定项目生成规则和管理工具。用户要求初始化已授权这些配置文件的创建；现有项目治理仍须遵守。
- 盘点/迁移：先只读列出已有规则及冲突，不直接套模板覆盖。
- 维护：检查身份、权限、导航和任务结构，按实际差异更新已经采用的规则；不凭模板摘要覆盖项目定制。

阅读 [配置步骤](references/setup-guide.md)，需要对照覆盖范围或接 CI 时再读 [规则与适配边界](references/rule-map.md) 和 [CI 接入](references/ci-integration.md)。要写入的完整内容已在 `assets/project/`，不是要求使用者另找模板。

## 初始化路径

1. 从用户给定工作目录确定项目根，读取已有入口规则，记录 Git 分支、HEAD 和未提交改动。无 Git 的工程也可使用，不替其创建仓库。区分代码根和文档/工具根；不扫描全盘；按内置敏感规则（`.env*`、`credentials*`、`secrets*`、`.aws/`、`.docker/`、密钥文件等）跳过内容读取，未识别形态须显式补充排除。
2. 全面扫描目标项目的源码、配置、依赖清单、文档、CI、测试和资源元数据，建立文件摘要与排除项基线；核读已有规则及真实入口，再适配技术栈、模块导航、声明的门禁和变更边界。未知职责/生成器留待确认，不猜权限或复制个人设置。
3. 用包内脚本生成只读变更预览。命令中的 `<skill-dir>` 是本 SKILL.md 所在目录，`<project-root>` 必须是用户授权的现有目标目录。

   ```text
   python <skill-dir>/scripts/bootstrap.py plan --project <project-root> --project-name <name> --platform codex --diff
   python <skill-dir>/scripts/bootstrap.py apply --project <project-root> --project-name <name> --platform codex
   ```

   平台可多选 `codex claude cursor trae workbuddy opencode` 或 `all`。plan 不写文件。apply 先检查整批冲突；冲突退出 2，整批不写入。人工已有入口会保留，已有不同内容的配置不会被覆盖。已有受管文件有定制时，先比较并人工合并；不删除后重装规避冲突。
4. 按 [配置合同](assets/project/Docs/ai/configuration.md) 填写 profile、context-index、能力和提交约定。由获授权维护者在 policy 登记本人账号和最小范围；初始用户表、所有角色的路径均为空。迁移时保留既有文件类型、代码附加范围、内容归属及专项确认，新增授权需要项目负责人确认。
   重构类项目的意图契约、文档权威登记与产物基准随包部署：`Docs/ai/task-contract.md`、`Docs/ai/authority.md`、`Docs/ai/golden/`、`tools/ai/contract_check.py`。包内的 `public-type-baseline.txt` 只有说明头，初始化后由维护者运行 `python tools/ai/contract_check.py baseline --paths <模块根> --out Docs/ai/public-type-baseline.txt` 生成真实清单；不覆盖项目已有契约与基准。
5. 在目标根运行：

   ```text
   python tools/ai/check_env.py check
   python tools/ai/check_env.py whoami --user <registered-user> --role <declared-role>
   python tools/ai/check_env.py identity --user <registered-user> --role <declared-role>
   ```

   `identity` 只写被忽略的 `.ai-local.json`，不会授予角色；`whoami` 不写。岗位声明冲突时保持只读，换人可用 `clear-identity` 清缓存。检查通过只证明本次管理检查有效，构建、功能、性能与平台实际加载分别验证。
6. 对所选 AI 平台开新会话，要求它报告读过的规则、身份来源、允许路径和真实门禁，再用一个小的只读定位任务检查导航。没有实测证据时保留 `runtime_load=not_tested`。工具缺失、权限不足或构建不可用时记录具体原因，继续不依赖它们的准备。

## 核心入口、全面扫描与适配

根 AGENTS.md 在 500 token 内直接保留原则、开始任务、身份/路径与敏感边界、协作和交付要求；Unity 版另保留资源/程序集/生成物/设备验收边界。详细流程仍按 rules.json 唯一维护，摘要不增加第二套规则定义。使用包内完整核心模板，保留分段和可执行步骤，不在安装后再手写一份更短摘要。生成时同时检查根核心完整性和包含人工旧文/标记的全文预算；不满足则整批报告冲突，保留原文。项目路径适配与重新核计按配置合同执行。

plan/apply 自动扫描整个授权项目树（不是仅预读少量目录），生成 `Docs/ai/project-baseline.json` 与 `Docs/ai/project-adaptation.md`，并以可证事实适配 profile/context。盘点含覆盖率、文件摘要、Git基点、技术栈、模块、已有规则、声明的门禁及证据、待确认项。AI 还须核读关键来源和冲突，再完成目标项目的适配；静态检测不能替代语义判断。扫描不会给账号赋权，不把候选/声明命令写成已执行。

二进制只记元数据；内置规则识别的凭据/本机配置、缓存和外部链接不读取内容（未识别形态须显式排除），超大文本/不可读文件明确报告缺口；不称为全仓语义或运行审查。初始化后的日常任务按导航定向读取，不反复全扫。详细字段、500 token 口径和升级方式见 [配置合同](assets/project/Docs/ai/configuration.md)。

## 日常管理

| 意图 | 入口 |
| --- | --- |
| 规则路由、导航时效、台账验收、项目 skill 清单 | `python tools/ai/check_env.py check` |
| 当前身份与范围 | `python tools/ai/check_env.py whoami` |
| 清理本机身份缓存 | `python tools/ai/check_env.py clear-identity` |
| 定向查模块 | `python tools/ai/check_env.py context --query <keyword>` |
| 候选变更路径检查 | `python tools/ai/check_env.py scope --user <user> --paths <relative-path> ...` |
| 多人或跨会话任务 | `Tasks/index.json` + `Docs/ai/task-template.md` |
| 重构任务的契约判定 | `python tools/ai/contract_check.py check --contract Tasks/<task>-contract.md`；判定器自检 `... selftest` |

规则唯一来源由 `rules.json` 登记，字段说明统一在 `configuration.md`。导航 stale/unknown 要复核真实入口；技能文件被发现不等于平台已加载。任务来源修订未确认可先建候选，完成时核对负责人和验收证据。

重构、重建或替换既有设计的项目必须生成并维护 `Docs/ai/task-contract.md`、`Docs/ai/authority.md` 与 `Docs/ai/golden/`，单任务契约存 `Tasks/<task>-contract.md`。收口前运行 `python tools/ai/contract_check.py check --contract Tasks/<task>-contract.md`，退出码 0 才进入工程门禁；`python tools/ai/contract_check.py selftest` 可在临时目录自检判定器，不写项目目录。

## 已包含的质量与工具环境

C1–C5 已随初始化部署：[行为评测与架构约束](assets/project/Docs/ai/quality-workflows.md)、[工具信任/环境自检/脱敏扫描](assets/project/Docs/ai/tool-integrations.md)。在目标根先运行 `python tools/ai/environment.py doctor` 和 `python tools/ai/evaluate.py validate`。依赖图和真实轨迹由项目工具提供，未配置的必需门禁不能记为通过。

C6 Serena、C7 Context7、C8 OpenSpec 为按需接入，全部复用 profile.capabilities，不另建工具/任务状态表。先核来源、固定版本、许可和数据边界；本包不安装第三方软件、不自动上传项目或执行任意接入命令。完整用法已在上述随包文档，无需另找模板。

## 交付

列出生成/合并/冲突文件、仍未配置的事实、身份来源、检查命令/退出码、平台加载和 CI 执行状态。不得把“文件存在”“audit 报告”说成已认证或已强制阻断。无需修改全局模型、沙箱、插件、代理角色、Git 分支或服务端设置。

交付前回读目标项目的实际 AGENTS.md，确认 `check` 的根入口报告 `core_matches=true` 且预算通过；预览或模板截图不能代替实际落盘结果。

常见误区：把样板用户当真实授权；只复制 AGENTS 而漏掉工具；已有工程直接覆盖；把静态检查等同工程验收。对应处理是空授权起步、完整安装、先比较合并、分别报告证据。
