# tools/analysis/ · 会话证据分析脚本

[docs/CODEX-MULTIAGENT-BENEFIT.md](../../docs/CODEX-MULTIAGENT-BENEFIT.md) 的全部数字由这批脚本产出
（纯标准库，`python -X utf8` 直接跑）。它们**只读** Codex 会话与状态库，输出到 `~/`，不改本仓库。

| 脚本 | 作用 | 输出 |
| --- | --- | --- |
| `codex_probe_meta.py` | 只读首行，列出会话清单（结构探明第一步） | `~/codex_meta.json` |
| `codex_probe_sample.py` | 抽样打印事件行原始结构 | 控制台 |
| `codex_probe_items.py` | 打印 `item_completed` 的 item 结构与 usage 字段 | 控制台 |
| `codex_extract.py` | 把 `rollout-*.jsonl` 压成统一事件流（唯一原始提取层） | `~/codex_events_<prefix>.jsonl` 等 |
| `codex_metrics.py` | 按分段计算 A 委派结构 / B 成本 / C 质量 / D 返工 | `~/codex_metrics_<prefix>.json` |
| `codex_threads_index.py` | 从 `state_5.sqlite` 取全量线程索引（补 rollout 丢失区间） | `~/codex_threads_index.json` |
| `codex_timeline.py` | 分天行为、AGENTS.md 内容 sha、模型档位时间线 | 控制台 |
| `codex_selfcheck.py` | 口径自检：同一动作的两条记录路径是否相等 | 控制台 |
| `codex_report_check.py` | **报告守门员**：把报告引用的关键数字从机读结果重算并逐条断言 | 控制台，FAIL 时 exit 1；输入缺失 exit 2 |
| `verify_raw.py` | 独立复核管线 A：另一套实现重算计数与 token | `~/verify_raw_out.txt` |
| `audit_quality.py` | 独立复核管线 B：独立提取子代理 status / 字段 / turn 生命周期 | `~/audit_quality_out.txt` |

## 用法

```powershell
# 0) 结构探明（先看名字，再计数；只读首行）
python -X utf8 tools\analysis\codex_probe_meta.py

# 1) main 数据（本机 ~/.codex/sessions，方案期）
python -X utf8 tools\analysis\codex_extract.py --root "$env:USERPROFILE\.codex\sessions" --prefix main
python -X utf8 tools\analysis\codex_metrics.py --prefix main

# 2) backup 数据（方案前备份目录；路径按本机实际备份替换，见 docs §6.2）
python -X utf8 tools\analysis\codex_extract.py --root "$env:USERPROFILE\.codex\sessions-provider-backup-20260915-191028" --prefix backup
python -X utf8 tools\analysis\codex_metrics.py --prefix backup

# 3) 报告守门员需要 main + backup 两份指标；缺任一份按用法错误退出（exit 2）
python -X utf8 tools\analysis\codex_report_check.py
```

- 会写文件的脚本都有显式参数契约：`codex_extract.py` / `codex_probe_meta.py` / `codex_threads_index.py` 支持 `--help` + `--out` + `--dry-run` + `--force`（默认拒绝覆盖已有输出）；`codex_report_check.py` 支持 `--help` + `--main` / `--backup`。参数错误返回 exit 2，不会静默继续。
- 数据源默认 `~/.codex/sessions/**/rollout-*.jsonl` 与 `~/.codex/state_5.sqlite`（只读）；`audit_quality.py` 的路径可用环境变量 `CODEX_SESSIONS` / `CODEX_AUDIT_OUT` 覆盖。
- **重跑保护**：上面的命令在已有输出的机器上重跑会拒绝覆盖——加 `--force` 重跑，或加 `--dry-run` 只检查不写。`codex_metrics.py --prefix` 只接受 `main` / `backup`，输入文件缺失时 exit 2。
- 本目录是仓库内的权威副本；`~/` 下的同名脚本为历史运行副本，行为可能滞后，长期维护以本目录为准。
- 中间产物（`codex_metrics_*.json` 等）不入库；`.gitignore` 已排除常见输出模式。
