# codex/ · 全局协调层与子代理

本目录是 `~/.codex/` 的可版本化部分。**方向是 live → 仓库**：这里的文件由
`tools/sync-config.ps1` 从本机 Codex 配置快照而来；重建机器时由
`tools/install-codex-env.ps1` 反向安装回去。

## 文件

| 文件 | 模型 @ 档位 | 沙箱 | 职责 |
| --- | --- | --- | --- |
| [AGENTS.global.md](AGENTS.global.md) | 主线程 `gpt-6.1-sol` @ `xhigh` | `workspace-write` | **全局协调层**：角色、委派硬性否决、切分粒度、验证等级、提交门禁、红线 |
| [agents/architect.toml](agents/architect.toml) | `gpt-6.1-sol` @ `high` | `workspace-write` | 实现**已定设计**的切片；不做设计决策；缺信息则 `blocked` |
| [agents/mech.toml](agents/mech.toml) | `gpt-6-luna` @ `high` | `workspace-write` | 机械改动（重命名/格式化/模板/批量替换）；无设计判断 |
| [agents/explorer.toml](agents/explorer.toml) | `gpt-6-luna` @ `high` | `read-only` | 只读取证；不得写文件；只报观察，不给建议 |
| [agents/verifier.toml](agents/verifier.toml) | `gpt-6-sol` @ `high` | `workspace-write` | 独立跑门禁、复现、证伪；**不得改源码** |
| [agents/committer.toml](agents/committer.toml) | `gpt-6.1-sol` @ `medium` | `workspace-write` | 只审 staged diff 与口径一致性并机械分级；S0/S1 中止提交 |

五个文件的必需字段都是 `name`、`description`、`developer_instructions`；正文为英文（面向模型）。
`config.toml` **不在本目录**：它含机器特定 MCP 路径，按 [../docs/CODEX-SETUP.md §3.2](../docs/CODEX-SETUP.md) 在本机维护。

## 规则

- **不要直接编辑本目录**：下次 `sync-config.ps1` 会用 live 覆盖。要改规则，先改
  `~/.codex/AGENTS.md` 或 `~/.codex/agents/*.toml`，再快照。
- 五个 agent 文件与 `AGENTS.global.md` 的规则必须一致（同一套约束写在两处）；改完跑
  `tools/check-consistency.py`。
- `agents/*.toml` 与 `config.toml` 在 Codex 启动时读取——**改动后重启 Codex**。

## 安装/回滚

```powershell
# 预览：仓库 -> 本机（列出将新增/更新的文件）
powershell -NoProfile -File ..\tools\install-codex-env.ps1
# 执行：写入前把将被覆盖的文件备份到 %USERPROFILE%\.codex-backups\<时间戳>-codeplus\
powershell -NoProfile -File ..\tools\install-codex-env.ps1 -Apply
```

回滚：把备份目录里的文件按原相对路径拷回 `~/.codex/`，或重新编辑 live 后快照。
