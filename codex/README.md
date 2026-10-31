# codex/ · 全局协调层与子代理

本目录是 `~/.codex/` 的可版本化部分。**方向是 live → 仓库**：这里的文件由
`tools/sync-config.ps1` 从本机 Codex 配置快照而来；重建机器时由
`tools/install-codex-env.ps1` 反向安装回去。

## 文件

| 文件 | 模型 @ 档位 | 沙箱 | 职责 |
| --- | --- | --- | --- |
| [AGENTS.global.md](AGENTS.global.md) | 主线程 `gpt-6.1-sol` @ `xhigh` | `workspace-write` | **最小注入层（≤80 行）**：4 条不变量、状态指针表、5 条工作规则 |
| [DELEGATION.md](DELEGATION.md) | —（不自动注入） | — | **主线程按需读**：何时委派 / 预算上限（≤8）/ 六段 brief / 回报字段 |
| [agents/architect.toml](agents/architect.toml) | `gpt-6.1-sol` @ `high` | `workspace-write` | 实现**已定设计**的切片；填形状不发明形状；brief 不全则 `blocked` |
| [agents/mech.toml](agents/mech.toml) | `gpt-6-luna` @ `high` | `workspace-write` | 一条明确规则套到指定文件；需要判断就停 |
| [agents/explorer.toml](agents/explorer.toml) | `gpt-6-luna` @ `high` | `read-only` | 只读回答一个问题；每条结论带 `file:line`；不给建议 |
| [agents/verifier.toml](agents/verifier.toml) | `gpt-6-sol` @ `high` | `workspace-write` | 独立重跑门禁、复现、证伪；**不得改源码** |
| [agents/committer.toml](agents/committer.toml) | `gpt-6.1-sol` @ `medium` | `workspace-write` | 只判 staged diff 是否在 claim 内、门禁是否绿；否则拒绝提交 |

五个文件的必需字段都是 `name`、`description`、`developer_instructions`；正文为英文（面向模型）。
`DELEGATION.md` 位于同一层但**不在 Codex 的自动注入范围**——只有主线程在派活前读它。
`config.toml` **不在本目录**：它含机器特定 MCP 路径，按 [../docs/CODEX-SETUP.md §3.2](../docs/CODEX-SETUP.md) 在本机维护。

## 规则

- **不要直接编辑本目录**：下次 `sync-config.ps1` 会用 live 覆盖。要改规则，先改
  `~/.codex/AGENTS.md` 或 `~/.codex/agents/*.toml`，再快照。
- **规则层有体积预算**（`check-consistency.py` 的 `BUDGET_LINES`：`AGENTS.md` ≤80 行、
  `DELEGATION.md` ≤90 行、每个 `agents/*.toml` ≤70 行）。要加规则先删等量文本。
- **委派剧本不要搬回 `AGENTS.md`**：它是所有子代理都会读到的注入层，搬回去等于让每个子代理
  重新背上与它无关的规则。改完跑 `tools/check-consistency.py`。
- `agents/*.toml` 与 `config.toml` 在 Codex 启动时读取——**改动后重启 Codex**。

## 安装/回滚

```powershell
# 预览：仓库 -> 本机（列出将新增/更新的文件）
powershell -NoProfile -File ..\tools\install-codex-env.ps1
# 执行：写入前把将被覆盖的文件备份到 %USERPROFILE%\.codex-backups\<时间戳>-codex-env\
powershell -NoProfile -File ..\tools\install-codex-env.ps1 -Apply
```

回滚：把备份目录里的文件按原相对路径拷回 `~/.codex/`，或重新编辑 live 后快照。
