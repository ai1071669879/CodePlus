# skills/ · 项目级 AI 环境生成器

两个自包含 skill（Python 3.10+ 标准库，无外部依赖）。它们不是"提示词模板"，而是**生成器**：
在目标项目里落地一套可直接运行的项目级 AI 环境（规则、身份/权限、导航、任务、门禁、契约与检查器）。

| skill | 适用项目 | 产物要点 |
| --- | --- | --- |
| [project-ai-environment/](project-ai-environment/) | 任意通用项目 | `AGENTS.md` 核心入口、`Docs/ai/` 规则与配置、`tools/ai/` 检查器、意图契约、文档权威登记、产物基准 |
| [unity-ai-environment/](unity-ai-environment/) | Unity 工程 | 通用底座 + Unity 专属规则（资源/.meta、程序集/依赖、策划源表、设备验收、`unity_checks.py`） |

## 什么时候触发

- 「初始化 / 迁移 / 收敛项目的 AI 工作环境」「生成团队规则和检查工具」「接 CI 的 AI 门禁」。
- **普通功能开发不触发**：两个 skill 的 `description` 都明确排除日常编码任务。

## 生成物的关键机制（project-ai-environment）

- **意图契约**：重构类任务先写 `[Keep]/[Rewrite]/[Forbidden]/[Superseded]`，契约优先于"最小改动/复用优先"。
- **文档权威登记**：权威/参考/已失效/记录四档，避免把历史描述当现行要求。
- **产物基准**：把"像不像我预想"变成与基准逐行比较。
- **机器判定**：`tools/ai/contract_check.py` 校验禁止项、越界新增 public 类型、产物基准；
  退出码 `0` 通过 / `1` 违规 / `2` 不合法或未验证。

细节见 `project-ai-environment/assets/project/Docs/ai/`（该目录是模板母本）。

## 来源与镜像关系

- **唯一维护处是 `~/.codex/skills/<name>/`**；本目录是 live 的镜像，由
  `tools/sync-config.ps1` 用 robocopy `/MIR` 覆盖（排除 `__pycache__`、`.pytest_cache`）。
- 要改 skill：改 `~/.codex/skills/<name>/`，跑 `sync-config.ps1`，不要只改这里。
- 新机器安装：`tools/install-codex-env.ps1 -Apply` 会把本目录两个 skill 装到 `~/.codex/skills/`。

## 自检

改动 skill 后，在 skill 目录逐个跑其自带测试（入口是 `--skill` 参数的脚本，不是 pytest）：

```powershell
cd skills\project-ai-environment
python -X utf8 -B tests\test_review.py --skill .
python -X utf8 -B tests\test_bundle_upgrade.py --skill .
python -X utf8 -B tests\test_upgrade_tools.py --skill .
python -X utf8 -B tests\test_core_contract.py --skill .
# 其余 tests\test_*.py 同样带 --skill .
```

期望全部 exit 0。测试会实际 bootstrap 到系统临时目录，不写目标项目。
