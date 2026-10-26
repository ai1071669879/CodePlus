# 多 Agent 方案收益分析（2026-10-24）

> 本报告所有数字都由 `~/codex_extract.py` → `~/codex_metrics.py` / `~/codex_threads_index.py`
> 从原始日志重新计算，未复用任何历史结论里的数字。每条「实测」都附了能复现它的命令（见第 6 节）。
> 凡是算不出来的指标，直接写「不可测」并说明原因，不用估计值替代。
>
> 报告正文里引用的 **106 个关键数字**由 `~/codex_report_check.py` 逐条断言（从机读结果重算后比对），
> 实测 **0 条 FAIL**。命令：`python -X utf8 $env:USERPROFILE\codex_report_check.py`。

## 0. 结论摘要

**最强结论（逐条标注证据等级）**

1. **【已验证】上一轮「主线程 267 次 exec vs 14 次 spawn」的口径是错的，本次已定位错因。**
   本机日志里 `payload.type == "function_call"` 的 `payload.name` **从来没有 `exec_command`**
   （主线程取值 0 次，结构性恒为 0）。真正的 shell 调用有两条记录路径：
   ① `custom_tool_call`（`name` 恒为 `exec`，`input` 是 JS 源码）里嵌套的 `tools.exec_command(...)`；
   ② `item_completed` 里 `item.type == "CommandExecution"` 的结构化条目。
   按 ② 计，主线程窗口内实执行 **8,768 条命令**，子代理执行 **12,032 条**——不是 267，也不是 14。
   两条路径互相印证：嵌套 `exec_command` 8,655 ≈ `CommandExecution` 8,768。（§1.3、§3-A、§6.3）

2. **【已验证】既没有「单一方案生效日」，也无法从规格日志里拿到「方案前」基线。**
   `~/.codex/sessions/**/rollout-*.jsonl` 最早一条是 **2026-10-14T11:42Z**，当天就 spawn 了 7 个子代理；
   `~/.codex/AGENTS.md` 委派规则段落与 `agents/*.toml` 角色模板的 mtime（10-12/10-13）都早于它。
   而线程索引（`state_5.sqlite`）显示：**首次 `thread_spawn` 在 2026-09-23，2026-09-28/29 起规模化**；
   子代理线程:主线程的月度比值 7 月 0.18 → 8 月 0.40 → 9 月 0.97 → 10 月 **15.06**。
   → 真正的「方案」是分三步装起来的：能力(09-23~09-29) → 角色模板与委派规则(10-12/13) → 两次修订(10-19/10-22)。
   本报告因此用补充源取基线，基线跨了一代模型（§1、§2、§4-③）。

3. **【已验证】方案自己定义的「子代理报告格式」被 99.9% 执行，但方案自己定的「unverified 必须给出处置」
   一条都没被执行。** 方案前 755 份子代理终稿里 `status:` 字段出现率 **0%**；方案期四字段
   （`changed_files`/`evidence`/`assumptions`/`blockers`）存在率 **99.88%**（804/805），
   但四字段**有非空内容**的只有 **86.34%**。更关键：301 份 `unverified` 里只有 56.15% 之后出现过 status 记录，
   而这些记录里 85.29% 最终**仍是 unverified**，且全量日志里 `disposition` 字样**命中 0 次**。
   （§3-C；独立复核管线 B 的口径与数字）

4. **【已验证】turn 完成率没有提升，方案期内还在缓慢下降。** 主线程
   92.61%（基线）→ 92.96% → 91.96% → **89.55%**，中断率 6.76% → 7.04% → 8.04% → **8.96%**；
   子代理 95.90% → 99.49% → 99.28% → 97.80%。历史结论里的「完成率 78.2% → 97.2%」
   在两套数据、三种口径下都复现不出来。（§3-C、§3-E）

5. **【推断】委派把成本从主线程搬到了子代理，但没有证据表明单位工作量的总成本下降。**
   子代理计费输入占比 6.87%（基线）→ 36.66% / 46.78% / 46.24%（S1/S2/S3）；
   但「每 FileChange 项消耗 token」1.65M → 1.74M → 1.51M、「每 shell 命令消耗 token」
   174.8K → 177.7K → 149.3K，**没有单调改善**。方向一致但未证实。（§3-B）

**明确不能得出的结论**

- 不能得出「多 Agent 方案带来了净收益」。没有同时控制模型、任务类型、项目的对照期。
- 不能得出「每 turn credits 下降 X%」。**credits 在这套日志里不可测**（§3-B）：含 `credits` 的
  字段只有一个钱包状态对象，约 2.44 万次采样全部是
  `{"has_credits":false,"unlimited":false,"balance":"0"}`，没有任何 `credits_used/spent/consumed` 字段。
  历史值「1.14 → 0.68」没有数据源。
- 不能把「缓存命中率上升」「每 turn 成本下降」归因于委派：同期 turn 长度（响应/turn）从
  2.8 → 52.0 → 43.9 → 21.5，成本变化主要跟着 turn 长度走（§4-①）。
- 不能对 S3（近期）作百分比结论：它只有 **4 个主线程会话、67 个 turn**（§2）。

## 1. 数据来源与口径

### 1.1 三个数据源（第一个是任务指定的，后两个是为补「方案前基线」而另找的）

| 源 | 路径 | 规模 | 时间窗（UTC） | 用途 |
|---|---|---|---|---|
| 主源（任务指定） | `~/.codex/sessions/**/rollout-*.jsonl` | **480 文件 / 957 MB** | 2026-10-14T11:42Z ~ 2026-10-24T10:27Z | 方案期全部细粒度指标 |
| 补充源① | `~/.codex/sessions-provider-backup-20260915-191028/`（含 `sessions/` 352 + `archived_sessions/` 76） | **428 文件 / 1,412 MB** | 2026-06-05T02:29Z ~ 2026-09-15T09:27Z | **方案前基线 P0**（有完整事件流） |
| 补充源② | `~/.codex/state_5.sqlite` 的 `threads` 表（只读） | **1,520 条线程** | 2026-06-05 ~ 2026-10-24 | 线程级索引；覆盖 **09-16~10-13 这段 rollout 已丢失的区间** |

说明：`~/.codex/sessions/2026/06..09` 这些目录存在但是空的；同样的历史日志只保留在 `sessions-provider-backup-*`
和 `state_5.sqlite` 里。因此「方案前基线」只能来自补充源，这一点在 §4-③ 会被当作混淆变量处理。

### 1.2 会话与线程结构（实测，非文档推断）

- **480 个日志文件 / 474 个不同 session id**。差的 6 个是「续接文件」：同一 session id 有 2 个 rollout
  文件（例：`…01a13a23…` 出现在 10-14 和 10-15 两个文件）。**因此本报告一律以「文件」为会话身份**，
  否则线程会被错误绑定到首日。
- `thread_source` 分布：`user` **26**（主线程）/ `subagent` **294**（子代理）/ `guardian_review` **160**（审批代理）。
- 主线程 `cwd`：`D:\ProjRx\RxToolkits` 263 个文件、`D:\GYYX\seawar` 215、`D:\ProjRx\RxCsharp` 2。
- 子代理 `agent_role`：`architect` 109 / `explorer` 93 / `verifier` 57 / `mech` 27 / `committer` 7 / `default` 1。
- `spawn_agent` 调用 **301** 次，但规格 glob 内的子代理会话只有 294 个 → **差 7 个**。逐名核对
  `task_name` 与子代理 `agent_path`：这 7 个全部来自 **2026-10-14 那个最早的会话**
  （`worldrendering_gates`、`editor_test_gate`、`requirements_matrix`、`view_snapshots`、`world_lifecycle`、
  `graph_compiler`、`baseline_independent_verification`），其对应的子代理 rollout 文件在
  `~/.codex/sessions` 下不存在（**推断**：被清理或未落盘）。反向看，「有子代理会话但没有同名 spawn」
  的数量是 **0**，说明没有凭空多出来的子代理。
- 规格外还有 **5 个归档会话**（`~/.codex/archived_sessions/`：3 个主线程 + 2 个子代理，10-17~10-20），
  **未纳入本报告统计**。若纳入，主线程会话数为 29、子代理为 296。

### 1.3 工具名清单（**先打印名字，再计数**）

`response_item` / `payload.type == "function_call"`（模型真正发出的工具调用）：

| thread_source | 实际出现的 name 与次数 |
|---|---|
| `user`（主线程） | `spawn_agent` 301、`send_message` 666、`followup_task` 527、`wait_agent` 304、`request_user_input_async` 170、`sleep` 87、`list_agents` 84、`wait` 17、`request_user_input` 15、`interrupt_agent` 4 |
| `subagent` | `send_message` 1185、`wait_agent` 195、`sleep` 174、`wait` 105、`list_agents` 10 |
| `guardian_review` | （无） |

`response_item` / `payload.type == "custom_tool_call"`：`name` **只有 `exec`**（user 7,424 / subagent 9,828）。

`exec` 的 JS 源码里嵌套调用的 `tools.*(`（正则统计）：`exec_command` 8,655（user）/ 10,370（sub）、
`apply_patch` 1,393 / 789、`write_stdin` 525 / 538、`web__run` 57 / 23、`view_image` 47 / 1、
`clock__curr_time` 52 / 6、`mcp__codex_app__open_in_codex` 31、`mcp__codex_app__read_thread` 7、
`mcp__codex_app__load_workspace_dependencies` 1、`mcp__codex_app__list_threads` 1、`append` 1（误报）。

`event_msg` / `item_completed` 的 `item.type`：

| thread_source | item.type 与次数 |
|---|---|
| `user` | `Reasoning` 15080、`CommandExecution` **8768**、`SubAgentActivity` 2298、`AgentMessage` 1992、`FileChange` 1345、`UserMessage` 399、`CollabAgentToolCall` 304、`ContextCompaction` 96、`ImageView` 77、`McpToolCall` 40、`Extension` 144、`Plan` 8 |
| `subagent` | `Reasoning` 12110、`CommandExecution` **12032**、`AgentMessage` 2430、`SubAgentActivity` 1183、`FileChange` 790、`CollabAgentToolCall` 195、`Extension` 196、`ContextCompaction` 52、`ImageView` 2、`McpToolCall` 19 |
| `guardian_review` | `AgentMessage` 581、`Reasoning` 562、`UserMessage` 244 |

**关键结构结论**：`exec_command` 只能从 ②（`CommandExecution`）或 ①（嵌套正则）数，
从 `function_call.name` 数**永远得 0**。两个独立口径对得上：嵌套 `exec_command` 8,655 ≈
`CommandExecution` 8,768（差 113，0.7%，未逐条归因）。

**三条容易踩的坑（独立复核管线 B 实测确认）**：

1. **`event_msg.payload.type == "agent_message"` 实际是 0 条**。主线程收到的子代理消息，真实载体是
   `response_item.payload.type == "agent_message"`。本管线的报告取自子代理自己的 `task_complete`，
   所以不受影响；但任何想从「主线程中继」恢复报告的实现必须先认对载体。
2. **首条 user 消息会带 AGENTS.md 模板全文**（里面就有 `changed_files:` / `evidence:` 的示例）。
   在 user 消息上跑字段正则会产生数百条假报告。本管线只从子代理终稿取数，规避了这一点。
3. **同一份报告在日志里有多份落盘表示**（`item_completed` 的 `AgentMessage`、`task_complete.last_agent_message`、
   主线程中继副本）。三者必须去重，否则报告数会虚高 3 倍以上。本管线只取 `task_complete.last_agent_message`。

### 1.4 token / credit 事件的真实字段结构（grep 样本后确认）

两种记录并存，键名不同，**不能混用**：

```
token_usage_record.payload: { usage, turn_token_usage, thread_token_usage }
    usage            = 该次 API 响应的用量
    turn_token_usage = 该 turn 累计（跨响应累加值）
    thread_token_usage = 该线程累计
    键: input_tokens / cached_input_tokens / cache_write_input_tokens /
        output_tokens / reasoning_output_tokens / total_tokens

event_msg(payload.type=token_count).payload.info: { total_token_usage, last_token_usage, model_context_window }
    total_token_usage = 会话累计；last_token_usage = 最近一次响应
    另有 rate_limits.primary.used_percent（7 天窗口配额百分比）、plan_type、
        credits{has_credits, unlimited, balance}
```

**已实测校验**：`usage` 是单响应用量、`turn_token_usage` 是累计——
同一 turn 内 `sum(usage.input_tokens)` == 最后一个 `turn_token_usage.input_tokens`。
逐步打印过一次（某 turn 16 次响应，`sum(usage.in)=4,393,907`，最后一条 `turn_in=4,393,907`），
并对全库 **1,617 个 (文件,turn)** 做了同样检查：**不相等 0 个**（命令见 §6.3）。
所以**逐响应累加 `usage.input_tokens` 就是计费输入总量**；而把 `turn_token_usage` 跨行相加会严重高估。

**credits 不可测**：全库含 `credit` 的字段只有 `token_count.payload.rate_limits.credits`，
约 2.44 万次采样（`token_count` 事件数）全部为 `{"has_credits":false,"unlimited":false,"balance":"0"}`；
`balance` 从未非 `"0"`，`has_credits` 从未为 `true`，也没有任何
`credits_used / spent / consumed / delta` 字段。
→ **「每 turn credits」这个指标在本机日志上不存在可计算的定义。** 能用的替代信号只有
`rate_limits.primary.used_percent`（7 天滚动配额百分比，无法归因到单 turn）与 `plan_type`（`prolite` / `plus`）。

### 1.5 日期分组口径

**统一用 UTC 日**，取每个文件首行 `payload.timestamp`（ISO8601，带 `Z`）。本地时间 = UTC+8。
本数据上「UTC 日 / +8 本地日 / 目录名日期」三者恰好一致（没有任何会话首行落在本地 00:00–08:00 之间），
所以这一选择不影响任何结论。分天会话数（UTC）：
10-14 **1**、10-15 20、10-16 13、10-17 107、10-18 **0**、10-19 103、10-20 58、10-21 51、10-22 48、10-23 20、10-24 59。

> 口径冲突留档（已消除）：独立复核管线（`~/verify_raw.py`，另一套独立实现，不读本管线中间文件）
> 起初给出「10-18 = 23 个会话」的按日分布，与本管线（10-18 = 0）冲突。经复核，**是复核管线的 bug**：
> 它用 `strptime` 得到 naive datetime 后调用 `.astimezone(utc)`，PowerShell/Python 会把 naive 时间当本地
> 时间（UTC+8）解释，导致所有 UTC 小时 < 8 的会话被算到前一天。修正为 `dt.replace(tzinfo=timezone.utc)`
> 后，复核管线重跑得到与本报告**逐位一致**的 11 个日期计数，并确认 `2026/10` 下不存在 `18` 目录。
> 该 bug 只影响日期标签，不影响任何总数与按 `thread_source` 的汇总。

## 2. 分段依据

### 2.1 改动生效日怎么定位的（不看记忆里的日期，只看证据）

**(a) 配置文件 mtime（本地时间，直接证据）**

| 文件 | mtime（本地） | 折算 UTC |
|---|---|---|
| `~/.codex/agents/verifier.toml` | 2026-10-13 10:45 | 10-13 02:45 |
| `~/.codex/agents/explorer.toml` | 2026-10-13 11:39 | 10-13 03:39 |
| `~/.codex/agents/mech.toml` | 2026-10-13 18:01 | 10-13 10:01 |
| `~/.codex/AGENTS.md` + `agents/architect.toml` + `agents/committer.toml` | **2026-10-19 10:33** | **10-19 02:33** |
| `~/.codex/config.toml` | **2026-10-22 10:29** | **10-22 02:29** |

另有备份文件可证更早的改动：`agents/*.toml.before-6.1sol` = 10-12 10:17、`mech.toml.before-obsrule` = 10-08 15:34。
**`config.toml` 的 `[agents]` 段（`default_subagent_model = "gpt-6-luna"`、`default_subagent_reasoning_effort = "high"`、
`max_concurrent_threads_per_session = 6`）在 2026-10-10 的备份里就已经存在，且与今天逐字相同**——
所以窗口内这三次改动都**不涉及**子代理模型/并发上限。

**(b) 日志里的 AGENTS.md 内容指纹（间接证据）**

`world_state.payload.state.agents_md.text` 会记录当时生效的 AGENTS.md 全文，取其 sha1：

| sha | 项目 | 首次出现 | 末次出现 |
|---|---|---|---|
| `64fbaabded1c` | seawar | 10-14T12:56Z | 10-17T11:22Z |
| `c2cbeddcca56` | seawar | **10-19T03:58Z** | 10-24T10:10Z |
| `9543bb22980b` | RxToolkits | 10-17T03:05Z | 10-17T10:23Z |
| `ef86ae3ddbc5` | RxToolkits | **10-19T04:20Z** | 10-24T10:23Z |

两个项目的 AGENTS.md 内容都在 **10-17 之后、10-19 03:58Z 之前**换过一次，与 10-19 10:33 本地 mtime 吻合。

**(c) 行为突变（线程索引，覆盖日志已丢失的区间）**

`state_5.sqlite` 的 `threads` 表按 `source` 字段区分线程类型，逐日统计（完整表见
`~/codex_threads_index_out.txt`）：

| 月份 | 主线程 | 子代理线程 | 审批 | 子代理:主线程 |
|---|---|---|---|---|
| 2026-06 | 2 | 0 | 0 | 0.00 |
| 2026-07 | 11 | 2 | 30 | 0.18 |
| 2026-08 | 82 | 33 | 86 | 0.40 |
| 2026-09 | 123 | 119 | 109 | 0.97 |
| **2026-10** | **35** | **527** | **361** | **15.06** |

逐日看：**2026-09-23 出现第一条 `thread_spawn`**（`agent_path=/root/terrain_review`、`agent_role=null`），
**2026-09-28（51 个子代理）/09-29（46 个）开始规模化**，10-08~10-10 三天分别 77/44/69 个。

→ 结论：**多 Agent「能力」的时间点是 09-23～09-29；10-12/10-13 落地的是角色模板与委派规则；
10-19、10-22 是两次修订。不存在一个单一的「方案生效日」。**

### 2.2 分段与样本量

| 段 | 时间窗（UTC） | 定义依据 | 日志文件 | 主线程 | 子代理 | 审批 | 主线程 turn | 样本是否足够 |
|---|---|---|---|---|---|---|---|---|
| **P0 基线** | 2026-06-05 ~ 09-15 | 补充源①，早于任何 `thread_spawn` 规模使用 | 428 | **230** | 182 | 16 | 1,258 | 够（但模型/产品跨代，见 §4-③） |
| **GAP 过渡** | 2026-09-16 ~ 10-13 | rollout 已丢失，只有线程索引 | 0 | — | — | — | — | 只能做线程级，不能做指标 |
| **S1 方案期** | 2026-10-14 ~ 10-17 | 主日志最早一段 | 141 | **10** | 88 | 43 | 71 | 勉强（10 个主线程） |
| **S2 改写后** | 2026-10-19T02:33Z ~ 10-21 | AGENTS.md + architect/committer 模板 10-19 02:33Z | 212 | **12** | 113 | 87 | 112 | 勉强（12 个主线程） |
| **S3 近期** | 2026-10-22T02:29Z ~ 10-24 | config.toml 10-22 02:29Z | 124 | **4** | 93 | 27 | 67 | **不足**（4 个主线程） |
| （边界外残余） | 10-19 00:00–02:33、10-22 00:00–02:29 等 | — | 3 | 0 | 0 | 3 | 0 | 忽略 |

**样本量判断**：主线程会话总数只有 26 个（20 条不同线程），S3 只有 4 个。
所以本报告里凡涉及主线程的百分比，都必须读作「4~12 个会话上的比例」，**不足以支撑趋势结论**；
子代理侧样本大得多（S2 411 份报告、419 个 turn），子代理侧指标相对可信。

## 3. 指标对比

> 全部数字来自 `python -X utf8 ~/codex_metrics.py --prefix main` 与 `--prefix backup`
> （输出存档 `~/codex_metrics_main_out.txt`、`~/codex_metrics_backup_out.txt`，机读版 `~/codex_metrics_*.json`）。
> P0 一列的「wait」在旧版本是另一个工具（等 shell/目标，不是等代理），已单独处理，见 §4-②。

### 3-A 委派结构

| 指标 | 公式 | P0 基线 | S1 | S2 | S3 |
|---|---|---|---|---|---|
| 新建委派数 | 主线程 `spawn_agent` 调用数 | **61** | **106** | **115** | **80** |
| 复用次数 | `send_message` + `followup_task` | 262 | 425 | 601 | 167 |
| 主线程自执行 | 主线程 `CommandExecution` 条数 | **16,615** | **3,075** | **4,361** | **1,332** |
| 委派占比 | spawn / (spawn + 自执行) | 0.37% | 3.33% | 2.57% | 5.67% |
| 每次委派的平均复用轮数 | (send+followup) / spawn | 4.30 | 4.01 | 5.23 | 2.09 |
| 空转比 | (wait_agent + wait) / spawn | 4.30 | 0.92 | 1.59 | 0.50 |
| 每主线程会话 spawn | spawn / 主线程会话数 | 0.27 | 10.6 | 9.6 | 20.0 |
| FileChange 归属（子代理占比，按项） | sub 项 / 全部项 | **5.17%** | **32.06%** | **36.80%** | **46.85%** |
| FileChange 归属（按涉及文件数） | 同上 | 5.82% | 27.66% | 35.08% | 44.92% |

交叉校验（同一批动作在 `item_completed` 里的 UI 副本，应等于 spawn 数）：
`SubAgentActivity.started` = 106 / 115 / 80（与 spawn 完全一致）；
`CollabAgentToolCall.wait` = 95 / 169 / 40（与 `wait_agent` 的 95 / 169 / 40 完全一致）。
→ 说明 `function_call` 计数与 `item_completed` 计数是同一批事件的两种记录，**不能相加**。

读法提醒：
- 「委派占比 3.3%」是**按动作条数**算的（1 次 spawn 对 ~30 条 shell 命令），不代表时间或 token 的占比；
  按 token 算子代理占 36.7%~46.8%（见 3-B）。
- S3 的 5.67% 是 4 个会话上的比例（其中 1 个会话就 spawn 了 35~37 次），**不可外推**。

### 3-B 成本

| 指标 | 公式 | P0 基线 | S1 | S2 | S3 |
|---|---|---|---|---|---|
| 主线程 每响应输入 token（均值/中位） | Σ in / 响应数 | 152,085 / 157,028 | 188,972 / 184,833 | 200,886 / 199,006 | 203,510 / 202,022 |
| 主线程 每 turn 计费输入 | Σ in / turn 数 | 429,416 | 9,831,864 | 8,817,443 | 4,373,937 |
| 主线程 每 turn 未缓存 | Σ(in−cached) / turn 数 | 46,949 | 220,263 | 178,397 | 77,153 |
| 主线程 缓存命中率 | Σ cached / Σ in | **89.07%** | **97.76%** | **97.98%** | **98.24%** |
| 主线程 响应/turn（turn 长度） | 响应数 / turn 数 | **2.8** | **52.0** | **43.9** | **21.5** |
| 每 turn credits | Σ credits / turn 数 | **不可测** | **不可测** | **不可测** | **不可测** |
| 子代理 每 turn 计费输入 | Σ in / turn 数 | 44,536 | 2,117,748 | 2,113,586 | 1,404,721 |
| 子代理 缓存命中率 | Σ cached / Σ in | 88.18% | 97.17% | 96.04% | 96.25% |
| **子代理 token 占比** | sub Σin / 全部 Σin | **6.87%** | **36.66%** | **46.78%** | **46.24%** |
| 审批代理 token 占比 | guardian Σin / 全部 Σin | 0.79% | 1.36% | 1.05% | 0.76% |
| 计费输入合计 | Σ in（三段相加 = 3,572.3M） | 585.0M | 1,126.3M | 1,893.1M | 552.9M |
| 每 FileChange 项消耗 token | 合计 Σin / 全部 FileChange 项 | 0.11M | 1.65M | 1.74M | 1.51M |
| 每 shell 命令消耗 token | 合计 Σin / 全部 CommandExecution | 33.4K | 174.8K | 177.7K | 149.3K |

**「每 turn credits」的计算式（写出来是为了说明它为什么算不出来）**：

```
每 turn credits = Σ(每次 API 响应的 credits 消耗) / turn 数
```
分子在本机日志中不存在：唯一含 `credits` 的字段是
`token_count.payload.rate_limits.credits`，它是账户钱包状态
（`has_credits / unlimited / balance`），不是消耗量。约 2.44 万次采样全部为
`{"has_credits":false,"unlimited":false,"balance":"0"}`。→ 不可测。

**读法提醒（很重要）**：跨 P0 与 S 段的「每 turn」数字**不可比**，因为 turn 本身的含义变了：
旧版本一个 turn 平均 2.8 次 API 响应（一问一答式），方案期一个 turn 平均 52/43.9/21.5 次响应
（长会话、多工具循环）。所以「每 turn 输入从 429K 涨到 9.8M」不是成本恶化，
而是 turn 变长了 18 倍。**真正可比的量是「每响应输入」（152K→189K→201K→204K，缓慢上升，
因为上下文越装越多）和「每单位交付」（上表最后两行，无单调改善）。**

### 3-C 质量

| 指标 | 公式 | P0 基线 | S1 | S2 | S3 |
|---|---|---|---|---|---|
| 主线程 turn 完成率 | `task_complete` / `task_started` | **92.61%** | **92.96%** | **91.96%** | **89.55%** |
| 主线程 turn 中断率 | `turn_aborted` / `task_started` | 6.76% | 7.04% | 8.04% | 8.96% |
| 子代理 turn 完成率 | 同上 | 95.90% | 99.49% | 99.28% | 97.80% |
| turn 失败率 | 「报错 turn」/ turn 总数 | **无此事件** | 无 | 无 | 无 |
| 子代理终稿数 | 每 turn 一条 `task_complete.last_agent_message` | 755 | 192 | 411 | 178 |
| status = passed | 正则 `^status:\s*(\w+)` | **0（全无 status 字段）** | 91（47.4%） | 200（48.7%） | 44（24.7%） |
| status = unverified | 同上 | — | 44（22.9%） | 131（31.9%） | 112（62.9%） |
| status = failed | 同上 | — | 33 | 50 | 14 |
| status = blocked | 同上 | — | 24 | 22 | 7 |
| 无 status 字段 | 同上 | 755（100%） | 0 | 8（committer 用另一套合同形状） | 1 |
| 结构化报告合规率 | 同时含 changed_files + evidence + assumptions + blockers | **0 / 755 = 0%** | **192/192 = 100%** | **409/411 = 99.5%** | **178/178 = 100%** |
| `unverified` 未收敛 | 同 agent_path 后续 turn 无非 unverified 终态 | — | 35 / 44 | 87 / 131 | 100 / 112 |

**报告覆盖率的诚实说明**：本管线的报告只来自「子代理会话自己的 `task_complete.last_agent_message`」，
共 **781 份**。独立复核管线（`~/audit_quality.py`）改用三条 final-answer 通道（含主线程中继的
`response_item.payload.type == "agent_message"`）得到 **805 份**，多出的 **24 份（3.0%）**是
「子代理 rollout 缺失、只能从主线程中继恢复」的那部分。两边 status 分布一致：
`failed` 两边都是 **97**；`passed` 335 vs 347、`blocked` 53 vs 59、`unverified` 287 vs 301
（差口全部落在那 24 份中继报告上）。**结论方向不受影响。**

**独立复核给出的两个更强的结论（本报告采纳）**：

1. **合规率的严格版**：四字段「存在」是 804/805 = 99.88%，但四字段「有非空内容」只有
   **695/805 = 86.34%**（`changed_files` 里有 74 份是显式空的 `[]`）。→ 格式被 100% 遵守，
   但约 14% 的报告存在空字段；说「合规率 100%」时应限定为「字段存在率」。
2. **`unverified` 的处置在实践中不存在**：301 份 `unverified` 里，同一产出线程后续出现过 status 记录的
   只有 **169 份（56.15%）**，而这 169 份里后续最后一条**仍是 `unverified`** 的占 **85.29%**；
   全量日志里 `disposition` 字样**命中 0 次**。→ AGENTS.md 要求「每个 unverified 必须给四种处置之一
   并记录」，实测**没有任何一条被记录**。这是本次能给出的最硬的一条「规则未被遵守」的证据。

口径注解：

- **独立复核管线 B 的 turn 生命周期数字与本管线一致**（同一份日志、另一套实现）：
  user `251 started / 230 done / 20 aborted` → 完成率 91.63%、中断率 7.97%；
  subagent `798 / 791 / 6` → 99.12% / 0.75%；guardian `581 / 581 / 0` → 100%。
  与本管线分段数字的差（如 user 250 vs 251 个 turn）来自活跃日志增长与分段边界，**不是口径分歧**。
- **「turn 失败率」算不出来**：日志里没有 turn 级「失败」事件。`task_complete` / `turn_aborted` 之外没有
  第三种 turn 终态。可以替代的是「子代理 `status: failed` 报告占比」（S1 17.2% / S2 12.2% / S3 7.9%），
  但那是子代理任务的失败，不是 turn 失败。历史数字「12.5% → 0%」定义来源不明。
- `turn_aborted` 的 `reason` 实测只有 `interrupted`（用户按了 Esc/新消息打断），**不是系统报错**；
  把它叫「失败率」是错的，本报告称「中断率」。
- `unverified` 未收敛的判定只覆盖「再派发」一种处置：能观测到的是同一 `agent_path` 后续 turn 是否给出
  非 unverified 终态。主线程在正文里写「Accepted risk / Out of scope」这类 disposition 的文本
  无法结构化识别，所以 35/87/100 应读作**未收敛的下界**。

### 3-D 返工

| 指标 | 公式 | P0 基线 | S1 | S2 | S3 |
|---|---|---|---|---|---|
| 同一主线程内重复 `task_name` 的 spawn | 同名 task_name 出现 >1 次的额外次数 | 3 | 0 | 0 | 0 |
| 同一主线程内被改动 >1 次的文件路径占比 | count(path 出现>1) / 不同 path 数 | 52.2% | 38.7% | 42.9% | 45.2% |
| blocked 子代理报告数 | `status: blocked` 报告 | 0 | 28 | 22 | 3 |
| blocked 后 30 分钟内主线程再次派发/发消息 | 时间窗匹配 | — | 7（25%） | 17（77%） | 2（67%） |

- **`task_name` 重复这个指标基本失效**：主线程给每次 spawn 起的 task_name 是唯一化的
  （`terrain_runtime_survey`、`excel_inputs`…），所以「重复 spawn」只能测到 0。改用「同线程内同一文件
  被改动多次」作为返工代理：**38.7% → 42.9% → 45.2%，轻微上升**。
  P0 的 52.2% **不能与方案期直接比**：两版的 FileChange 产生方式不同——P0 主线程有 5,120 个 FileChange 项、
  嵌套 `apply_patch` 5,378 次；方案期主线程只有 1,345 个 FileChange 项、嵌套 `apply_patch` 1,393 次。
  同样的「改文件」在两版日志里被记账的粒度不一样，所以这行只能看方向、不能看数值。
- 「blocked 后由主线程接手」只能**推断**：可观测的是 blocked 报告之后 30 分钟内同一主线程是否再次
  `spawn_agent`/`send_message`/`followup_task`。S2 的 77% 明显高于 S1 的 25%，但两者样本只有 28/22 个
  blocked，且这不等于「主线程自己用 exec 接手」。**标为推断。**

### 3-E 与历史数字的差异对照（任务要求逐条说明）

| 指标 | 历史值 | 本次重算 | 判定 |
|---|---|---|---|
| fileChange 子代理占比 | 0.7% → 77.8% | 5.17%(P0) → 32.06% → 36.80% → 46.85% | 方向一致，**幅度对不上**；77.8% 在本数据上复现不出 |
| 每 turn 输入 token | 120,134 → 90,152 | 每响应 152K→189K→201K→204K；每 turn 429K→9.83M→8.82M→4.37M | **两套口径都不匹配**；历史数字找不到对应定义 |
| 每 turn 未缓存 token | 8,910 → 2,996 | 每 turn 46.9K→220K→178K→77K；每响应约 4.2K→3.6K | 数量级不对，历史值可疑 |
| 缓存命中率 | 92.6% → 96.7% | 89.07% → 97.76% → 97.98% → 98.24% | 方向一致，**数值不同** |
| 每 turn credits | 1.14 → 0.68 | **不可测** | 历史值**没有数据源** |
| turn 完成率 | 78.2% → 97.2% | 92.61% → 92.96% → 91.96% → **89.55%** | **方向相反且不可复现** |
| turn 失败率 | 12.5% → 0% | 无 turn 级失败事件；中断率 6.76%→7.04%→8.04%→8.96% | 定义不明，无法复现 |

**哪一版可能是错的**：至少「turn 完成率 78.2% → 97.2%」和「每 turn credits 1.14 → 0.68」这两条，
在本机日志上找不到可以产出该数值的口径，倾向于**上一版是错的**（或用了非本机日志的数据）。
「fileChange 子代理占比」「缓存命中率」方向一致但数值不可复现，倾向于**两版口径不同、历史版口径未写明**。

## 4. 混淆变量处理（逐条）

**① 任务类型 / 任务规模不同**——这是最强的混淆，且**没有真正消除**。
可观测的规模代理指标：

| 段 | 主线程 turn 中位 | 响应/turn | 每主线程会话计费输入（中位） | 单会话最大 |
|---|---|---|---|---|
| P0 | — | 2.8 | — | 76.4M（1,895 条命令那一个） |
| S1 | 5.5 | 52.0 | 44.9M | 243.0M |
| S2 | 6 | 43.9 | 40.6M | 451.6M |
| S3 | 15 | 21.5 | 71.3M | 129.5M |

同一段内单个会话的 token 跨度是 0.3M ~ 451.6M（1,500 倍），**段间均值差主要被个别巨型会话决定**。
处理方式：本报告主表同时给均值与中位数，并在 §3-B 末尾明确「跨段每 turn 成本不可比」。
**结论层面：凡不能按任务规模归一的指标，只写方向，不写百分比因果。**

**② 工具语义随版本变化**——已显式处理的坑。
旧版（P0）主线程 `wait` 有 5,504 次，那是**等后台 shell/目标**的工具；新版 `wait_agent` 才是等子代理。
若不分版本直接算「(wait_agent+wait)/spawn」，P0 会得到 94.52（荒谬值），S1 会得到 0.92。
处理：P0 的空转比只用 `wait_agent`（262/61 = 4.30），S 段用 `wait_agent+wait`；
并在 §1.3 把两版工具名清单分开列出。同理 `exec_command` 在旧版**确实是** `function_call` 的名字（927 次），
在新版恒为 0——这正是上一轮口径翻车的根源。

**③ 模型档位同期变化**——段内已排除，跨期无法排除。
- **段内（10-14~10-24）模型完全没变**（`turn_context` 全量统计）：
  主线程 `gpt-6.1-sol@xhigh`（106/159/80 次）、`architect` `gpt-6.1-sol@high`（78/133/61）、
  `explorer`/`mech` `gpt-6-luna@high`、`verifier` `gpt-6-sol@high`、审批 `codex-auto-review@low`。
  唯一新增是 `committer` `gpt-6.1-sol@medium`（10-19 起，13 次）。
  → **S1→S2→S3 之间的成本/质量变化，可以排除「模型换代」这个解释。**
- **跨期（P0 vs S）模型是 gpt-5.5 / gpt-5.6-sol / gpt-5.6-luna / gpt-6-astra / deepseek-v4 等多代混用**，
  且 CLI 大版本从 0.137 到 0.163。→ **P0→S 的任何成本变化都不能归因于委派策略。**
- 历史分析里提到的「主线程 medium → xhigh、architect gpt-6-sol → gpt-6.1-sol」确实发生过，
  但发生在 **10-08 与 10-10**（`config.toml.at-medium-20261008`、`config.toml.before-6.1sol-20261010`），
  **早于所有可用日志**。也就是说（**推断**，无法验证历史分析的实际取样区间）：历史版很可能把
  「模型换代」和「委派策略」放进了同一个前后对比，两者无法分离。

**④ 项目不同**——未消除，只标注分布。

| 段 | RxToolkits | seawar | 其它 |
|---|---|---|---|
| P0 | 84 / 428（19.6%） | 111 / 428（25.9%） | **233 / 428（54.4%）**，主要是 RxCsharp / RxStockEngine / dsh |
| S1 | 48 / 141（34.0%） | 93 / 141（66.0%） | 0 |
| S2 | 123 / 212（58.0%） | 87 / 212（41.0%） | 2 |
| S3 | 92 / 124（74.2%） | 32 / 124（25.8%） | 0 |

P0 一半以上是 RxCsharp 的库改造/单测任务，S2/S3 七成以上是 RxToolkits.Exporter 与 seawar GPUWorld 的
大重构。**工作性质不同 → 委派率与成本天然不同。** 本报告没有做「同项目同任务」的配对比较，
因为每个单元格的样本只有个位数。

**⑤ 样本量与日志覆盖**

- 主线程会话：S1 10 个、S2 12 个、S3 **4 个**。任何跨段的百分比都建立在两位数以下的样本上。
- 子代理侧样本足够（S2 411 份报告 / 419 个 turn），子代理侧结论相对可靠。
- token 覆盖：`token_usage_record` 覆盖 `user` 26/26、`subagent` 294/294、`guardian_review` **130/160**
  （30 个审批会话没有任何 token 记录）。所以「审批代理成本」是**下界**，好在它只占 0.76%~1.36%。
- **09-16 ~ 10-13 这 28 天没有任何 rollout 文件**，只有线程索引。这段恰好是「能力出现→规模化」的关键期，
  也是本报告最大的数据缺口。
- `spawn_agent` 301 次 vs 子代理会话 294 个：7 个差口见 §1.2。

**⑥ 观测本身的反身性（额外说明）**：主日志是**活跃日志**——本次分析运行期间仍有 2 个文件在增长
（+38,066 bytes）。所以重跑会有个位数到十位数的漂移。本报告数字以 `~/codex_metrics_*_out.txt`
存档时刻为准，差异量级不影响任何结论方向。

## 5. 结论与局限

### 5.1 能得出的（按证据强度）

1. **【已验证】工具名与字段口径**：`exec_command` 在 `function_call` 中恒为 0；shell 执行必须从
   `CommandExecution` item 或 `exec` JS 内嵌套调用计数。本次独立复核管线（`~/verify_raw.py`，
   另一套实现）在 spawn 301 / send_message 666 / followup 527 / CommandExecution 8,768(user) /
   FileChange 1,345(user) 等十几项上与主管线**逐项相等**。
2. **【已验证】多 Agent 的使用量在方案期是真实的、量级级的**：主线程 26 个会话里 spawn 301 次、
   复用 1,264 次（`send_message` 666 + `followup_task` 527）、子代理累计执行 12,032 条 shell 命令、
   承担 32%~47% 的 FileChange。
3. **【已验证】子代理报告格式合规率 0% → 99.5~100%**。这是唯一可以干净归因于配置文本改动、
   且跨了模型代也能成立的效果。
4. **【已验证】方案期内（10-14~10-24）模型档位未变**，因此该区间内的成本/质量差异不能再用
   「模型换代」解释——这一点排除了上一版分析里最容易被误用的解释。
5. **【已验证】turn 完成率没有改善**：92.61%（基线）→ 92.96% → 91.96% → 89.55%；
   中断率上升 6.76% → 8.96%。「完成率提升到 97.2%」不成立。
6. **【已验证】credits 不可测**，历史 credits 数字无数据源。
7. **【已验证】「unverified 必须给出处置」这条规则在实践中完全没有被执行**：301 份 `unverified` 里
   只有 56.15% 之后出现过 status 记录，且这些记录里 85.29% 最终仍是 `unverified`；
   全量日志里 `disposition` 字样命中 **0 次**。→ 这不是「收益」，而是**方案自身有一条规则未被落地**。

### 5.2 不能得出的

- **方案净收益**：没有「同模型、同项目、同任务类型」的对照期。P0 跨了一代模型；S1/S2/S3 之间
  任务组合也在变（S1 以 seawar 为主、S2/S3 以 RxToolkits 为主）。
- **因果**：不存在 A/B 或断点回归设计；每次配置改动都同时伴随任务组合变化，且 S3 只有 4 个会话。
- **成本下降**：每单位交付成本（每 FileChange 项、每 shell 命令）**没有单调改善**，
  不能写成「方案降低了成本」。
- **交付质量提升**：子代理 `status: passed` 占比没有上升（47.4% → 48.7% → 24.7%），
  `unverified` 占比大幅上升（22.9% → 31.9% → 62.9%），未收敛数 100/112。这些变化可能与角色组合
  （S3 里 explorer/verifier 占比更高）有关，**不能读成质量变差**，更不能读成变好。
- **任何基于 S3 的百分比结论**。

### 5.3 需要更多数据才能判断的

1. **「委派节省了多少主线程上下文」**：需要按任务规模归一的配对实验（同一任务，一次委派一次不委派）。
2. **「unverified 是否真的未收敛」**：需要主线程 disposition 文本的结构化记录；本报告的 100/112
   只是下界。
3. **「reuse/spawn 从 4.01 → 5.23 → 2.09」是策略变好还是任务变短**：需要把 followup 的原因打标
   （新任务 / 返工 / 补充信息）。
4. **09-16~10-13 这 28 天**：需要找回那段 rollout（`state_5.sqlite` 显示有 1,041 个线程的
   `rollout_path` 已不存在），否则「能力出现→规则落地」这段因果链只能是推断。
5. **credits/计费**：需要能记录实际消耗 credits 的日志字段（当前只有钱包余额）。

## 6. 复现方法

### 6.1 脚本（`~/` 与本仓库 `tools/analysis/` 各一份，纯标准库，`python -X utf8` 直接跑）

| 脚本 | 作用 | 输出 |
|---|---|---|
| `~/codex_extract.py` | 从原始 `rollout-*.jsonl` 提取统一事件流（唯一的原始提取层） | `~/codex_events_<prefix>.jsonl`、`~/codex_reports_<prefix>.jsonl` |
| `~/codex_metrics.py` | 按分段算 A/B/C/D 全部指标 | 控制台 + `~/codex_metrics_<prefix>.json` |
| `~/codex_threads_index.py` | 从 `state_5.sqlite` 取全量线程索引（含 rollout 丢失区间） | 控制台 + `~/codex_threads_index.json` |
| `~/codex_timeline.py` | 分天行为表、AGENTS.md 内容 sha 时间线、模型档位时间线 | 控制台 |
| `~/codex_probe_meta.py` | 只读首行，排查会话清单（结构探明第一步） | `~/codex_meta.json`（内含 480 条 meta） |
| `~/codex_probe_sample.py` / `~/codex_probe_items.py` | 打印 `function_call` / `custom_tool_call` / `item_completed` 的原始样本结构 | 控制台 |
| `~/codex_selfcheck.py` | 口径自检：同一动作的两条记录路径是否相等、token 累计语义是否闭合 | 控制台（存档 `~/codex_selfcheck_out.txt`） |
| `~/codex_report_check.py` | **报告守门员**：把本报告引用的 106 个数字从机读结果重算并逐条断言 | 控制台，有 FAIL 时退出码 1 |
| `~/verify_raw.py`（独立复核管线 A：计数/token） | 复核 480 文件计数与 token，另一套实现 | `~/verify_raw_out.txt` |
| `~/audit_quality.py`（独立复核管线 B：质量） | 独立提取子代理报告 status/字段/turn 生命周期（三条 final-answer 通道） | `~/audit_quality_out.txt` |

> 本仓库副本在 [`tools/analysis/`](../tools/analysis/README.md)：同名脚本与其用法说明。中间产物仍输出到
> `~/`（`codex_metrics_*.json` 等），不入库。

### 6.2 关键命令原文

```powershell
# 0) 结构探明（先看名字，再计数）
python -X utf8 $env:USERPROFILE\codex_probe_meta.py
python -X utf8 $env:USERPROFILE\codex_probe_sample.py 2
python -X utf8 $env:USERPROFILE\codex_probe_items.py

# 1) 提取（主源 = 方案期；补充源① = 方案前基线）
python -X utf8 $env:USERPROFILE\codex_extract.py --root "$env:USERPROFILE\.codex\sessions" --prefix main
python -X utf8 $env:USERPROFILE\codex_extract.py --root "$env:USERPROFILE\.codex\sessions-provider-backup-20260915-191028" --prefix backup

# 2) 分段指标（报告第 3 节全部数字）
python -X utf8 $env:USERPROFILE\codex_metrics.py --prefix main
python -X utf8 $env:USERPROFILE\codex_metrics.py --prefix backup

# 3) 分段依据：分天行为 / AGENTS.md sha / 模型档位
python -X utf8 $env:USERPROFILE\codex_timeline.py

# 4) 线程索引（覆盖 rollout 已丢失的 09-16~10-13）
python -X utf8 $env:USERPROFILE\codex_threads_index.py

# 5) 分段边界证据（配置文件 mtime，本地时间）
Get-ChildItem "$env:USERPROFILE\.codex\AGENTS.md","$env:USERPROFILE\.codex\config.toml" |
    Select-Object Name, LastWriteTime
Get-ChildItem "$env:USERPROFILE\.codex\agents" -Filter *.toml | Select-Object Name, LastWriteTime

# 6) 单点抽查：credits 字段到底是不是消耗量（打印原文）
Get-ChildItem "$env:USERPROFILE\.codex\sessions" -Recurse -Filter *.jsonl |
    Select-String -Pattern '"credits"' -List | Select-Object -First 1 -ExpandProperty Line
```

### 6.3 一次性自检（同一批动作的两条记录路径必须相等，token 累计语义必须闭合）

```powershell
python -X utf8 $env:USERPROFILE\codex_selfcheck.py
```

实测输出（存档 `~/codex_selfcheck_out.txt`）：

| 自检 | 结果 |
|---|---|
| `spawn_agent`（function_call） vs `SubAgentActivity.started`（item） | **301 = 301，一致** |
| `wait_agent`（function_call） vs `CollabAgentToolCall.wait`（item） | **499 = 499，一致** |
| 嵌套 `tools.exec_command` vs `CommandExecution` 条数 | 19,025 vs 20,800（差 1,775 = 2.3%，来自 `write_stdin` 续写等其它调用路径，未逐条归因；**应接近不必相等**） |
| turn 生命周期闭合 | tstart 1,627 = tdone 1,598 + tabort 26 + 未闭合 3 |
| **token 语义**：每个 turn 内 `sum(usage.in)` 是否等于最后一条 `turn_token_usage.in` | 检查 **1,617** 个 (文件,turn)，**不相等 0 个** → 口径成立 |
| 全库 `sum(usage.input_tokens)` | **3,572,350,273**（另一条独立复核管线：3,572,544,289，差 0.005%，来自活跃日志增长） |

最后一行是整份报告最重要的口径证据：如果 `usage` 是累计值，这 1,617 个 turn 里会出现大量不相等；
实测 0 个，说明「逐响应累加 usage = 计费输入总量」成立，§3-B 的所有 token 数字都建立在这个已验证的语义上。

### 6.4 报告守门员（防止手抄错）

```powershell
python -X utf8 $env:USERPROFILE\codex_report_check.py
```

输出 106 条 `PASS/FAIL` 断言（样本量、A/B/C/D 四类共 106 个数字），末尾打印
`断言 106 条，FAIL 0 条`，有 FAIL 时退出码 1。它断言的是「报告正文的数字」与
「`~/codex_metrics_main.json` / `~/codex_metrics_backup.json` 重算值」的一致性。

---

**报告生成方式**：本文所有表格数字由 `~/codex_metrics.py --prefix main|backup` 与
`~/codex_threads_index.py` 直接产出，没有手工填写。若需复核任一数字，按 §6.2 顺序重跑即可。
