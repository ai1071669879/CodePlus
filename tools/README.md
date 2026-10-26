# tools/ · 同步与校验

**全局环境**与**项目技能**的工具严格分开：前四个脚本按模块分两组，互不跨模块。

| 脚本 | 模块 | 方向 | 作用 |
| --- | --- | --- | --- |
| [sync-config.ps1](sync-config.ps1) | Codex 全局环境 | live → 仓库 | 写指南、镜像 `codex/`、跑一致性 |
| [install-codex-env.ps1](install-codex-env.ps1) | Codex 全局环境 | 仓库 → live | 安装 `AGENTS.global.md`、`agents/*.toml`；写入前备份 |
| [sync-skills.ps1](sync-skills.ps1) | 项目技能 | live → 仓库 | 镜像两个 skill 到 `skills/`；仓库侧旧内容先备份 |
| [install-skills.ps1](install-skills.ps1) | 项目技能 | 仓库 → live | 安装两个 skill；live 侧先备份 |
| [sync-guide.py](sync-guide.py) | 全局环境 | live → 指南 | 把 `AGENTS.md` 嵌入指南 §3.1，同步 §0/§4.1 与版本日期，重生成模板 |
| [check-consistency.py](check-consistency.py) | 全局环境 | 校验 | 19 条表内规则 + 4 项附加检查（TOML 占位符 / 指南纯度 / 实证表述 / 版本日期） |
| [verify-repo.ps1](verify-repo.ps1) | 两模块 | 校验 | 本机一致性（依赖 `~/.codex`）：8 项，见仓库 README |
| [check-links.py](check-links.py) | 仓库 | 校验 | 文档相对链接（不检查 skill 资产模板） |
| [analysis/](analysis/README.md) | 证据分析 | 只读 | 产出 [收益分析](../docs/CODEX-MULTIAGENT-BENEFIT.md) 全部数字的会话脚本 |

## 常用

```powershell
# 全局环境：改完 live 配置后（先预览）
powershell -NoProfile -File D:\ProjRx\CodePlus\tools\sync-config.ps1 -Preview
powershell -NoProfile -File D:\ProjRx\CodePlus\tools\sync-config.ps1

# 项目技能：改完 ~/.codex/skills 后
powershell -NoProfile -File D:\ProjRx\CodePlus\tools\sync-skills.ps1

# 重建机器（先预览，再 -Apply）
powershell -NoProfile -File D:\ProjRx\CodePlus\tools\install-codex-env.ps1
powershell -NoProfile -File D:\ProjRx\CodePlus\tools\install-codex-env.ps1 -Apply
powershell -NoProfile -File D:\ProjRx\CodePlus\tools\install-skills.ps1
powershell -NoProfile -File D:\ProjRx\CodePlus\tools\install-skills.ps1 -Apply
```

## 约定

- **PowerShell 脚本必须是 UTF-8 with BOM**：本机 PowerShell 5.1 会把无 BOM 的中文按 GBK 误读，
  表现为「字符串缺少终止符」这类诡异解析错误。
- **用 `powershell`（5.1）跑，不要用 `pwsh`**。若报 `not digitally signed`，加 `-ExecutionPolicy Bypass`
  （仓库脚本未签名；本机曾出现仅 CodePlus 目录下的 .ps1 被该策略拦下，加 Bypass 即通过）。
- Python 脚本用 `python -X utf8`；只用标准库。
- 退出码：`0` 成功；`1` 校验/一致性失败；`2` 用法或契约错误（部分脚本）。
- 全局环境的 `sync-config.ps1` 支持 `-SkipCodex`（只改文档时更快）；技能同步不做模块交集。

## 已知风险（使用前读）

| 风险 | 触发条件 | 兜底 |
| --- | --- | --- |
| 技能镜像用 `/MIR` 覆盖目标侧 | live/仓库任一侧有未快照的改动 | 写入前备份到 `backups/<ts>/`（仓库侧）或 `~/.codex-backups/`（live 侧） |
| `install` 不删除 live 独有的 `agents/*.toml` | live 残留实验 agent | 无（脚本不猜删除；人工清理后快照） |
| `verify-repo` / `check-consistency` 依赖 live | 新克隆、换机、CI | 先 install；不要接无 live 的 CI |
| 源缺失 | 仓库被裁剪或误删 | `install-*` 检测 `missing-source` 并 exit 1 |
