# AGENTS · CodePlus

本仓库是 **AI 工程环境本身**（Codex 全局环境 + 项目技能 + 同步工具），不是可运行产品。

## 严格分离（第一条规则）

- **Codex 全局环境**（`docs/CODEX-SETUP.md`、`codex/`、`~/.codex/AGENTS.md`、`agents/*.toml`）
  **不得出现任何 skill 相关内容**：不写 skill 名称、不写 `[[skills.config]]`、不写技能加载策略。
- **项目技能**（`skills/<name>/`）**不得出现 Codex 全局环境内容**：不写全局协调层、不写
  `agents/*.toml`、不写全局 `AGENTS.md`、不写本仓库的同步脚本。
- 需要同时提到两者时，只允许在**仓库索引**（根 `README.md`、本文件）里并列指路，不写进任一模块正文。

## 改动的正确顺序

**全局环境**：

1. 改 live 源头：`~/.codex/AGENTS.md`、`~/.codex/agents/*.toml`。
2. `powershell -NoProfile -File tools\sync-config.ps1 -Preview` → 确认后去掉 `-Preview`。
3. `python -X utf8 tools\check-consistency.py`，期望 exit 0。

**项目技能**：

1. 改 live 源头：`~/.codex/skills/<name>/`。
2. `powershell -NoProfile -File tools\sync-skills.ps1`。
3. 各自跑 skill 自带测试（`tests\test_*.py --skill .`）。

只改 `docs/CODEX-SETUP.md` 手写章节时可直接编辑；**§3.1 与 §4 表格是生成区，改了会被覆盖**。

反方向（仓库 → live）用 `tools\install-codex-env.ps1` 与 `tools\install-skills.ps1`，只在重建机器时使用。

## 边界

- 不修改 `~/.codex/config.toml`：它含机器特定 MCP 路径，本仓库只提供指南 §3.2 的模板。
- 不把凭据、`auth.json`、会话日志、数据库、备份目录放进本仓库。
- `skills/` 是 `~/.codex/skills/` 的镜像：不要只改仓库侧，否则下次快照被覆盖。
- 生成区（指南 §3.1、§4 表格、`docs/CODEX-AGENTS-TEMPLATES.md`、`codex/` 快照）不得手改。

## 编码与运行约定

- PowerShell 脚本保存为 **UTF-8 with BOM**（本机 PowerShell 5.1 会按 GBK 误读无 BOM 中文）。
- Python 一律 `python -X utf8`；只用标准库；新增脚本需自带 `--help` 与退出码语义。
- 改同步/校验脚本后，跑 `verify-repo.ps1`（8 项）与 `check-consistency.py`，两者都过才算完成。

## 交付证据

声明"已同步/已修复"前附：命令原文、退出码、决定性输出。没有实际输出的一律写未验证。

`check-consistency.py` 与 `verify-repo.ps1` 读取本机 `~/.codex`，属于**本机一致性**校验，不能当作纯仓库门禁接进 CI；新克隆先 `install-codex-env.ps1 -Apply` 与 `install-skills.ps1 -Apply`。
