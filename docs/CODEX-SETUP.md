# Codex 多 Agent 调度 · 配置指南

**版本**：2026-10-31
**适用**：Windows + Codex Desktop/CLI，ChatGPT 登录
**用途**：从零重建本机 Codex 的「最小注入层 + 角色定义 + 机器执行层」配置

> 本文只讲三件事：**怎么配**（文件、字段、命令）、**为什么这么定**、**怎么验证**。
> **不含**会话统计、性能指标与故障排查日志——那些属于分析报告，不属于配置指南。
>
> **语言约定**：本指南用中文；`AGENTS.md`、`DELEGATION.md`、`agents/*.toml` 的**内容用英文**——
> 它们直接面向模型，英文在技术约束上歧义更小、也便于与上游文档对齐。

---

## 0. 方案概览

**规则层只保留「线程读不到、工具拒绝不了」的部分。** 其余内容分给文件指针与脚本退出码，
构成下面四层：

```
注入每个线程（≤80 行，体积预算）    <HOME>\.codex\AGENTS.md      4 条不变量 + 状态指针表 + 5 条工作规则
主线程按需读（62 行）    <HOME>\.codex\DELEGATION.md   何时委派 / 预算上限 / brief 六段 / 回报字段
角色专属（每个 ≤52 行）  <HOME>\.codex\agents\*.toml   我是谁 / 不许决定什么 / 报告字段
机器执行（脚本与文件）    tools\slice.py + 项目门禁      写域互斥 / 越界拒收 / gate=绿才算 done
```

**分界线是「上下文依赖度」，不是难度**——能被一份 brief 文件完整描述的工作才外派；
需要对话、用户澄清或跨切片判断的留在主线程。

| 角色 | 模型档位 | 写入权限 | 定位 |
|---|---|---|---|
| **主线程** | `gpt-6.1-sol` @ `xhigh` | 可写源码 | **所有需要完整上下文的工作**：架构与设计、领域形状、跨上下文集成、接口一致性、验收 |
| `architect` | `gpt-6.1-sol` @ `high` | 可写源码 | 实现一份**已定设计**的切片；填形状不发明形状；brief 不全就 `blocked` |
| `mech` | `gpt-6.1-terra` @ `high` | 可写源码 | 把一条明确规则套到指定文件；一旦需要判断就停 |
| `explorer` | `gpt-6.1-terra` @ `high` | 只读 | 只读回答一个问题，每条结论带 `file:line`；不给建议、不做设计决定 |
| `verifier` | `gpt-6-sol` @ `high` | 可写工作区，禁止改源码 | 独立重跑门禁、复现、证伪；源码不动，只给裁决 |
| `committer` | `gpt-6.1-sol` @ `medium` | 可写工作区（需写 `.git`），禁止改源码 | 只判两件事：staged diff 是否在 claim 内、门禁是否绿；否则拒绝提交 |

四条精简原则（以后想加规则时的判据）：

1. **工具能拒绝的，不写进规则**——写域、状态词、报告字段、门禁、预算 → 一个脚本。
2. **文件能读的，不放进上下文**——契约、切片表、authority、门禁输出 → 指针 + 按需读。
3. **代码形状承载设计**——设计先以接口骨架提交，子代理只填实现，不需要"理解设计"。
4. **净删优先**——新增必须在同一改动里删掉等量文本；规则层有行数预算，超了先删再加（§8.2）。

---

## 1. 前置条件

| 项 | 要求 | 说明 |
|---|---|---|
| Codex 版本 | ≥ 0.153.0（**未验证的下限**） | 见下方说明 |
| 登录方式 | ChatGPT 账号 | 登录后由 Codex 维护凭据；该方式**不出现在 `config.toml` 里** |
| 套餐 | Plus 或以上 | 额度按模型折算 |
| 网络 | 能访问 OpenAI | 直连不可达时需代理；`respect_system_proxy = true` 下走系统代理 |
| 系统 | Windows 10/11 | 部分安装/更新操作需要管理员 |

> **版本要求是推断值，不是经验下限。** 字段用法来自官方配置参考，但**没有逐字段核实过
> 哪个版本开始支持**。本机当前版本（`0.155.0-alpha.9`，命令 `codex --version`）只代表这台
> 机器，**不能作为最低版本依据**。若在更低版本上失败，先怀疑版本，再怀疑配置。

---

## 2. 文件清单

### 2.1 本机运行时（Codex 读取）

```
<HOME>\
└── .codex\
    ├── AGENTS.md              ← 最小注入层：4 条不变量 + 状态指针（注入每个线程）★核心
    ├── DELEGATION.md          ← 委派剧本：只有主线程在派活前读，子代理看不到
    ├── config.toml            ← 主配置（模型、沙箱、插件、MCP、信任项目）
    ├── agents\
    │   ├── architect.toml     ← 实现主线程已定的切片（不做设计决策）
    │   ├── mech.toml          ← 机械执行代理（无设计判断）
    │   ├── explorer.toml      ← 只读侦察代理
    │   ├── verifier.toml      ← 独立验证代理（跑门禁、证伪）
    │   └── committer.toml     ← 提交门禁代理（只审 staged diff）
    └── （其余为 Codex 运行时目录，自动维护）

<PROJECT_ROOT>\                ← 每个项目可选
├── AGENTS.md                  ← 项目专属规则（可选）
├── Tasks\<task>\              ← 任务状态（布局由项目自己的 AGENTS.md 定义；§2.4 给一种约定）
└── .codex\config.toml         ← 项目级插件/MCP（可选）
```

### 2.2 本指南仓库中的全局环境部分

本仓库同时存放其他模块（见仓库根 `README.md`），它们与 Codex 全局环境**严格分开**，不属于本指南范围。
本指南只维护以下路径：

```
<REPO_ROOT>\
├── docs\
│   ├── CODEX-SETUP.md               ← 本指南（唯一维护处）
│   └── CODEX-AGENTS-TEMPLATES.md    ← 五个 agents/*.toml 的完整正文（§4.2，由脚本生成）
├── codex\
│   ├── README.md                    ← 本目录规则与安装/回滚说明
│   ├── AGENTS.global.md             ← = ~/.codex/AGENTS.md
│   ├── DELEGATION.md                ← = ~/.codex/DELEGATION.md
│   └── agents\*.toml                ← = ~/.codex/agents/*.toml
└── tools\
    ├── sync-config.ps1              ← live → 仓库快照 + 一致性（改配置后跑这个）
    ├── install-codex-env.ps1        ← 仓库 → live 安装（重建机器时跑这个）
    ├── sync-guide.py                ← 把 live 配置写进本指南（§3.1/§4，生成区）
    ├── check-consistency.py         ← 6 条规则 + 5 项附加检查（含体积预算）
    ├── verify-repo.ps1              ← 本机一致性校验（8 项）
    ├── check-links.py               ← 文档相对链接检查
    ├── slice.py                     ← 写域认领与门禁记账（claim / verify / done / status）
    └── analysis\                    ← 多 Agent 收益分析的会话证据脚本
```

`codex/` 是 live 的完整快照，**包含 `DELEGATION.md`**。两个方向各司其职：**日常改配置用
`sync-config.ps1` 快照进仓库**；**换机或重建用 `install-codex-env.ps1` 从仓库安装**。
仓库不含 `config.toml`（含机器特定 MCP 路径，见 §3.2）。

### 2.3 ⚠️ 两个易错点

**① 全局层是 `<HOME>\.codex\AGENTS.md`，不是 `<HOME>\AGENTS.md`**

官方加载规则：

| 层级 | 位置 | 取值 |
|---|---|---|
| **全局** | `$CODEX_HOME/AGENTS.override.md`，否则 `$CODEX_HOME/AGENTS.md` | **只取第一个非空文件** |
| **项目** | 从项目根（通常 Git 根）逐层走到当前目录 | 每层取 `AGENTS.override.md` → `AGENTS.md` → fallback 名单，**每层最多一个** |
| `CODEX-AGENTS-TEMPLATES.md` | 配套模板（非 Codex 读取） | 五个 `agents/*.toml` 的完整正文，供从零复原时复制（§4.2） |

`<HOME>\AGENTS.md` 属于**项目层**——只有当前工作目录是家目录时才在加载链上。
把全局规则写在那里，换到项目目录就失效了。

**② 全局与项目级是「拼接」，不是「覆盖」**

官方原文：*Codex concatenates files from the root down, joining them with blank lines.
Files closer to your current directory override earlier guidance because they appear
later in the combined prompt.*

- 两层**同时进入 prompt**，全局在前；**通用规则放全局一次即可**，项目文件只写项目特有的
- 合并后总大小受 `project_doc_max_bytes` 限制（**默认 32 KiB**），超出**静默截断**，
  且项目级排在后面，**先被截掉**

```toml
project_doc_fallback_filenames = ["TEAM_GUIDE.md"]   # 让别的文件名也当指令文件
project_doc_max_bytes = 65536                        # 默认 32768
```

### 2.4 委派怎么落地

> 本节的 `Tasks/…`、`slices.json`、`briefs/` 属于**项目环境**的约定，不是 Codex 全局层的一部分；
> 具体路径由项目自己的 `AGENTS.md` 指定，全局 `AGENTS.md` 只要求「项目里能查到任务状态」。
> 本仓库提供的 `tools/slice.py` 是可选工具：要用就把它复制到项目自己的 `tools/` 并把路径写进项目 `AGENTS.md`。

只讲三件事，细则在 `<HOME>\.codex\DELEGATION.md`：**主线程派活前读，子代理看不到它**。

**① 预算与 brief 文件**：普通任务 2–4 个切片，大型并行 5–8 个，**硬上限 8**——需要更多说明
切分错了，重新切或留主线程做。一片 = 一个写者 = 一个门禁。派活前写
`Tasks/<task>/briefs/<slice>.md`，spawn 消息只发这个路径 + 切片 id。
brief 是**六段**：`slice`（含 executor）/ `paths` / `reuse` / `interfaces` / `facts` / `gate` / `stop`。

**② 写认领与门禁记账**：把本仓库的 `tools/slice.py` 复制到项目 `tools/`（可选，项目自己决定路径），
见 §3.1 的 Working rules）：

| 命令 | 作用 | 拒绝条件（exit 1） |
|---|---|---|
| `init --task-dir Tasks\<task> --task <id> --gate "<命令>"` | 建 `slices.json` | 已有注册表（`--force` 才重置） |
| `claim --id <slice> --owner <角色> --paths <路径...>` | 认领写域 | 与在飞切片的路径重叠；切片已 `completed` |
| `verify --id <slice> --changed <路径...>` | 核对改动是否在认领内 | 有文件在认领外（`OUTSIDE CLAIM`） |
| `done --id <slice> --changed <路径...>` | 记账完成 | 门禁非 0（`NOT DONE`）或改动越界 |

状态存在 `Tasks/<task>/slices.json`，压缩或换会话后读它即可重建"做到哪了"；`status` 打一张表。
脚本自带 `selftest`（8 个场景：重叠认领、红门禁、越界、completed 后重认领等）。

**③ 报告固定字段**：`status` / `slice` / `changed_files` / `reused` / `gate` / `assumptions` /
`blockers`。`passed` 只允许与门禁 exit 0 同时出现，且 `changed_files` 必须在认领内；
**缺 `status` 按 `unverified` 处理**。子代理报的 finding 是主线程决策的输入，不是工作项。

---

## 3. 全局配置

### 3.1 `<HOME>\.codex\AGENTS.md`（最小注入层，≤80 行）

**这是注入每个线程（含子代理）的唯一规则文本。** 它只保留两类内容：

- **不可读的不变量**——交付=门禁、单写者、事实在文件、停而非猜：没有对应文件可读，
  也没有哪条命令能替它拒绝；
- **状态指针**——契约、切片表、authority、记录四样东西在哪（`Tasks/<task>/…`、`docs/ai/authority.md`）。

**被移出去的东西**：委派剧本 → `DELEGATION.md`（主线程按需读，不进子代理首屏）；
写域与门禁判定 → `tools/slice.py` + 项目自己的 gate 命令；角色边界与报告字段 →
`agents/*.toml`；设计方法 → 代码骨架（stub-first）。**能被工具拒绝的约束不写进规则**——
散文的遵守率取决于当次注意力，脚本的遵守率是 exit 1。

内容用**英文**（面向模型）。以下是可直接使用的完整内容，由 `tools/sync-guide.py` 从 live 同步，
**不要手改这一段**：

````markdown

# AGENTS (Global)

Injected into every thread, including subagents. It holds only what a thread cannot read
from the repository and what no tool can enforce. Anything a command can reject, or a file
can state, lives there instead of here.

## Who decides

- The main thread owns design, decomposition and acceptance.
- A subagent executes the one slice it was given. It does not decide; it reports.

## Four invariants

1. **Delivery is the gate, not a claim.** A slice is done only when its gate command exits 0
   and every changed file is inside its claimed paths. Anything else is `unverified`.
2. **One writer per path.** Claim paths before editing. A path claimed by another in-flight
   slice is not yours: overlap means re-slice, never merge.
3. **Truth is in files.** The task state — scope, claimed paths, authoritative documents and
   the gate output — is the record. Conversation memory and summaries are not evidence.
4. **Stop instead of guessing.** Stop and report `blocked` for an open design choice, a
   missing interface, a spec conflict, or anything touching credentials — name what is
   missing. A minor spec ambiguity is not that class: state the assumption you are taking,
   proceed, and record it under `assumptions`. One round trip beats a wrong answer; it
   should not be spent on something a reasonable default settles.

## Where the state is

The project's own `AGENTS.md` names the files that hold: the slice's scope and gate command,
the registry of claimed paths, which documents are authoritative, and the gate output.
Read that file first. If the project has none, work directly in the project root — your
reviewable diff plus the gate you actually run are the record. Do not invent a task
registry; ask only when the work genuinely needs multi-session coordination or an
acceptance decision you cannot make.

## Working rules

- Read the project's task state first, then claim your paths there before editing.
- Read every file you change, and every file the task state lists as reusable, before editing.
- Run the gate the task names. Do not invent a different gate.
- Do not change governance files (any `AGENTS.md` or project rule document) unless that is the task.
- No credentials, no publishing, no commit unless the task says so.

## Delegation

Delegation is the default, not an exception. When work can be split into disjoint slices,
spawn subagents instead of doing it inline: keep this thread's context on design,
integration and acceptance. **This file explicitly authorizes delegation** — the runtime
asks for an explicit request from the user, `AGENTS.md`, or a skill, and this is it.

Main thread only: read `DELEGATION.md` when you are about to spawn. Hard ceiling 8 slices
per task, one writer per path. If the brief cannot be written as a file, do it yourself.

Every spawn passes `agent_type`: `architect` (implementation), `mech` (mechanical edits),
`explorer` (read-only survey), `verifier` (independent check), `committer` (commit gate).
Omitting it yields a generic `worker` that loses the role's instructions and model. Read-only
surveys and commit gates are delegated too — do not do multi-file investigations or commits
inline.

## Skills by role (global)

Role skill sets belong to the **role**, not to a project. Read the named `SKILL.md` only when
the task needs it; do not load skills outside your role's set. A project may narrow this
further — its `AGENTS.md` lists the project skills it allows.

- main thread: `design-patterns`, `test-driven-development`
- architect: `test-driven-development`, `design-patterns`
- mech: none (mechanical edits need no skill)
- explorer: `design-patterns`
- verifier: `test-driven-development`
- committer: none

Paths are `~/.codex/skills/<name>/SKILL.md`. When a plugin ships a same-named skill, use the
path above, never the plugin copy.

## Machine facts

- Codex sandbox modes: `read-only`, `workspace-write`, `danger-full-access`.
- Command network access is disabled by default; enable it deliberately per thread.
- This machine is Windows with PowerShell 5.1 — use `powershell`, not `pwsh`.

````

#### 3.1.1 `<HOME>\.codex\DELEGATION.md`（主线程按下需读）

62 行，**只给主线程**：子代理既看不到这个文件，也看不到派活那段对话。五个部分——
`Whether to delegate`（三条外派条件 + 四条"自己做"，判据是 **brief 能不能写成文件**）、
`Budget`（2–4 / 5–8，硬上限 8）、`The brief is a file`（六段模板与指针要求）、
`When it comes back`（固定字段；`passed` 的条件）、`When it goes wrong`（冲突按路径重切、
红门禁先修基线）。内容用英文，由 `sync-config.ps1` 一并快照到仓库 `codex/DELEGATION.md`。

### 3.2 `<HOME>\.codex\config.toml`

````toml
# ============================================================================
# 全局配置：<HOME>\.codex\config.toml
#
# 本文件可以直接保存使用——下面所有**未注释**的行都是有效配置。
# 依赖你自己路径的段落（MCP、受信任项目）**已注释**，需要时再解开并填值；
# 不解开不影响 Codex 启动。
# ============================================================================

# --- 沙箱与搜索 -------------------------------------------------------------
sandbox_mode = "workspace-write"
web_search = "live"           # cached(官方默认) | indexed | live | disabled
service_tier = "default"
model_verbosity = "medium"

# --- 主线程模型：架构与设计、跨上下文集成、验收 ------------------------------
model = "gpt-6.1-sol"
model_reasoning_effort = "xhigh"

# --- 子代理默认值（会被 agents/*.toml 的显式设置覆盖）-----------------------
[agents]
default_subagent_model = "gpt-6-luna"
default_subagent_reasoning_effort = "high"
max_concurrent_threads_per_session = 6

# --- 沙箱内网络：本方案主动开启，不是官方默认值 -----------------------------
# 官方默认「命令网络访问关闭」。开启后沙箱不再拦截命令联网；
# 但 web search / MCP / 插件走各自独立通道，不受此项控制（见 §7.19）。
[sandbox_workspace_write]
network_access = true

# --- 记忆：全部关闭（原因见 §5）--------------------------------------------
# 注意 [features] 段里的 memories 与 [memories] 段是两个不同的开关，两个都要关。
[features]
memories = false

[memories]
generate_memories = false
use_memories = false
disable_on_external_context = true

# --- MCP：不要手写这一段 -----------------------------------------------------
# 内置 MCP（如 node_repl）的 [mcp_servers.*] 由 Codex 自己生成并维护：
# command / env 里含 runtime hash 路径（形如 ...\runtimes\cua_node\<hash>\bin\...），
# Codex 更新时会自己改写。手写一份只会在下次更新时失效或被覆盖。
# 需要启用/禁用时，在项目级只覆盖 enabled（见 §6.2），不要复制完整定义。
# 所以这一段**无需任何配置行**——首次运行时 Codex 会自己生成。

# --- 受信任项目（可选；开启前必须换成你自己的真实路径）----------------------
# 项目级配置只在受信任项目加载。路径必须小写、用反斜杠，且反斜杠要转义。
# 不确定就先别开——不影响 Codex 启动。
# 示例（把 D:\\YourProject 换成真实路径后取消注释）：
#[projects."d:\\yourproject"]
#trust_level = "trusted"

# --- 插件：需要时再加 -------------------------------------------------------
# 同一个表只能出现一次。下面把表名换成真实插件名后取消注释；
# 需要开启就把 enabled 改成 true——不要为同一个插件写两遍表。
#[plugins."example-plugin@example-marketplace"]
#enabled = false

````

> **每个子代理的具体模型档位在各自的 `agents/*.toml` 里定义**，
> `[agents]` 段只提供默认值，会被 agent 文件里的显式设置覆盖。

---

## 4. 子代理定义

五个文件放在 `<HOME>\.codex\agents\`，每个 **≤52 行**（五个合计约 7 KB）。它们只写三样东西：
**我是谁**（`name` / 模型档位 / 沙箱）、**我不许决定什么**、**报告字段**。
全局协议（不变量、状态表、工作规则）在 §3.1 已经注入，**这里不再重复**——
重复的副本只会先漂移，然后被当成两套规则。

**必需字段**：`name`、`description`、`developer_instructions`。`description` 决定模型如何选中它，
必须写清**能做什么 + 不能做什么**。内容用**英文**。

### 4.1 五个 agent 的档位与职责边界

| 文件 | 模型 @ 档位 | 沙箱 | 职责边界（`description` 摘要） |
|---|---|---|---|
| `architect.toml` | `gpt-6.1-sol` @ `high` | `workspace-write` | 实现**已定设计**的切片；不做设计决策、不新增抽象与文件；缺信息则 `blocked` |
| `mech.toml` | `gpt-6.1-terra` @ `high` | `workspace-write` | 只做机械改动（重命名/格式化/模板/批量替换）；无设计判断 |
| `explorer.toml` | `gpt-6.1-terra` @ `high` | `read-only` | 只读取证；不得创建/修改/删除任何文件；可上报观察到的风险（只报不修） |
| `verifier.toml` | `gpt-6-sol` @ `high` | `workspace-write` | 跑门禁、复现、证伪；**不得改源码**；只给裁决 |
| `committer.toml` | `gpt-6.1-sol` @ `medium` | `workspace-write` | 只判 staged diff 是否在 claim 内、门禁是否绿；否则拒绝提交；**不得改源码** |

五个文件都写「**不做设计决定**」：缺信息就报 `blocked` 并点名缺什么。
报告字段统一为 `status` / `slice` / `changed_files` / `reused` / `gate` / `assumptions` / `blockers`
（`explorer` 与 `verifier` 的 `changed_files` 固定为 `[]`）。
观察与建议的边界见 §7.21。

### 4.2 完整 TOML 模板

五个文件的完整正文**不在本指南内**——它们各含自己的报告格式与停止条件，逐字镜像会随每次调整
失效，而**失效的镜像比没有镜像更危险**（照旧版复原会得到错误配置）。正文在配套文件里：

```text
CODEX-AGENTS-TEMPLATES.md      ← 五个 agents/*.toml 的完整正文（tools/sync-guide.py 生成）
```

复原时按该文件把五段 TOML 分别另存为：

```text
<HOME>\.codex\agents\architect.toml
<HOME>\.codex\agents\mech.toml
<HOME>\.codex\agents\explorer.toml
<HOME>\.codex\agents\verifier.toml
<HOME>\.codex\agents\committer.toml
```

`developer_instructions` 的结构是**角色定位 → 动手前 → 动手时 → 报告前 → 报告字段**（五段）。
**手上没有模板文件时**，不必照抄本机文件——按 §4.1 的档位与职责边界自行撰写这五段即可；
归档时以 `<HOME>\.codex\` 下的实际文件为准，**重启 Codex** 后生效。

---

## 5. 关键决策与理由

| 决策 | 理由 |
|---|---|
| **主线程用 `gpt-6.1-sol @ xhigh`** | 架构、设计、跨上下文集成都需要完整上下文，只有主线程持有；最高档给它 |
| **`architect` 用 `gpt-6.1-sol @ high`** | 只做「已定设计的具体实现」，不需要设计推理；上下文由 brief 给全 |
| `mech` 用 `gpt-6-luna @ high` | 只做机械改动，判断量低。**正因如此，它的活必须是机械的**——一旦需要判断就该换 `architect` |
| `verifier` 用 `gpt-6-sol @ high`、沙箱 `workspace-write` | 主要是跑命令 + 核对输出；构建/测试会写 `bin/`、`obj/`、缓存，`read-only` 下跑不了 |
| **规则层只保留「不可读、不可验」** | 能被工具拒绝的写进脚本（遵守率是 exit 1），能从文件读的给指针；否则规则越写越多、越写越没人看 |
| **把规则层从 90,040 字符压到约 12,375 字符** | 四条原则：工具能拒绝的不写进规则 / 文件能读的不放进上下文 / 代码形状承载设计 / 净删优先。委派剧本移出注入层是其中最大的一刀 |
| **委派剧本独立成 `DELEGATION.md`** | 委派决策是主线程的事；留在注入层等于让每个子代理都读一遍无关内容。现在按需读，不进子代理首屏 |
| **职责按「上下文依赖度」而非「难度」划分** | 分界线是**能不能被一份 brief 完整描述**。设计留给唯一持有完整上下文的主线程（§7.18） |
| **主线程定架构与设计，`architect` 只实现** | 早期让子代理做设计推理，但它看不到用户澄清、调查过程与跨切片影响（§7.12、§7.13） |
| **禁止按规格章节切分任务** | 否则规格的章节数变成文件数、规则数变成用例数（§7.17） |
| **子代理「上报观察，不给建议」** | 禁的是**建议**不是**信息**：阻塞与带指向的观察必须报，提案/排序/偏好/"下一步"禁止（§7.21） |
| **状态词由证据决定** | `passed` 只与门禁 exit 0 + 改动在认领内同时成立；其余一律 `unverified`，由固定报告字段与 `slice.py done` 拦住空口声明（§7.15） |
| **memories 全关** | ① 注入全局且不区分 cwd，多项目互相串注入 ② 2,500 token 上限是中间截断，最新条目最先丢 ③ 无已发表基准证明提升成功率 |
| 插件/MCP 默认关闭、项目级开启 | 每个插件都往系统提示加工具定义；MCP 注入完整工具定义，开销最大 |
| 保留轻量插件全局开启 | 纯指令、开销小、通用 |
| **不用 codex-router** | 它是跨厂商方案（Codex 当父 + 其他厂商模型当子）；本项目目标是稳定准确，跨厂商有合规与兼容风险 |
| 语言风格不写进全局 | 全局是最小注入层；语言/工具链风格属项目规范，写在项目 `AGENTS.md` |
| **12 字段契约表（superseded）** | 已废除：切片形状固定为六段 brief，按 agent 裁剪的四种契约不再存在（§7.23） |
| **`Shape First` 三问必答（superseded）** | 已废除：设计改由 stub-first 承载——骨架先提交，子代理只填实现（§7.17） |
| **委派触发表分三类（superseded）** | 已废除：触发表不再注入；何时外派写在 `DELEGATION.md`，判据是「brief 能不能写成文件」（§7.22） |
| **验证分四档 + 机械触发（superseded）** | 已废除：交付只有一条判据——契约点名的 gate exit 0，且改动在认领内（§7.15） |

### 5.1 插件 / MCP 的按需分配规则

两者都会往系统提示注入内容，**注入越少，每轮越省、主线程越不容易被噪声污染**。
统一原则：**默认关，按项目开；能全局通用的才留全局。**

判断顺序：每个项目每天都用 → 全局 `true`；只服务特定类型任务 → 全局 `false` 按项目开；
捆绑 MCP 服务器/连接器 → 全局 `false`（开销最大）；纯指令、无外部依赖且确实通用 → 可留全局 `true`。

**MCP 要分两类**：**内置 MCP**（`node_repl`、`cua_repl`）的 `command`/`env` 含 runtime hash 路径，
由 Codex 生成并维护，**不做统一开关**（手写 `enabled` 可能在下次更新时被改写），用不到时在项目级覆盖；
**第三方 MCP** 按上面的原则：全局 `false` 保留定义，项目里**只覆盖 `enabled`**。
判断本机有没有落实策略，看的是**第三方 MCP**。

---

## 6. 项目级配置（可选）

**整个 §6 都是可选的。** 方案核心全在全局层，只配全局即可运行。
项目级只在两种情况需要：**按项目开关插件/MCP**，或有**项目专属规则**。

> 项目级文件**只在项目被标记 `trusted` 时加载**。

### 6.1 项目级 `AGENTS.md`（可选模板）

```markdown
# AGENTS

<项目名> 项目工作规则。**通用工作约定与子代理委派规则见全局 `~/.codex/AGENTS.md` 与
`~/.codex/DELEGATION.md`**，本文件只写本项目特有内容。

## 项目约定

- <技术栈特定的前置检查>
- <生成代码 / 依赖目录的边界>
- <最小构建/验证命令>

## 门禁命令

- 构建：`<命令>`
- 测试：`<命令>`
- 架构测试：`<命令>`
- 分析器：`<命令>`

## <可选的更细切分约定>

如本项目目录结构与全局默认切分方式差异较大，在此说明按什么维度切分。
```

> **不要**把通用工作方式（取证要求、委派协议、凭据禁读）复制到每个项目——那些放全局。
> 两者是**拼接**关系，重复写等于白占上下文。

### 6.2 项目级 `.codex\config.toml`（可选模板）

````toml
# ============================================================================
# 项目级：<项目>\.codex\config.toml
# 只覆盖按项目变化的项；其余继承全局。
# ============================================================================

# 沙箱策略（按项目风险决定）
sandbox_mode = "workspace-write"

[sandbox_workspace_write]
network_access = true

# 只在该项目启用的插件——最小形式即可。
# 表名替换为真实插件名；不同插件可以并列，同一个插件只能出现一次。
[plugins."example-plugin@example-marketplace"]
enabled = true

# 只在该项目启用的 MCP——最小形式即可，全局已有完整定义
[mcp_servers.node_repl]
enabled = true

````

> 项目级配置只在**受信任项目**加载。若项目未在全局 `[projects."<路径>"]` 里标为
> `trusted`，`<项目>\.codex\config.toml` 会被忽略。

> ⚠️ **不要**复制 MCP 的完整定义（尤其 `command` 与 `env`）。
> 那些路径含机器特定 hash，会随 Codex 更新失效。**全局那份由 Codex 自动生成并维护**，
> 项目级只覆盖 `enabled` 即可。

### 6.3 项目级「意图契约 + 权威登记 + 切片表」（可选，重构类项目建议开）

全局层只规定「设计不在子代理手里」，项目层负责**落到文件与命令**。四个产物：

| 产物 | 作用 |
|---|---|
| `Tasks/<task>/contract.md` | 契约：`[Keep]`/`[Rewrite]`/`[Forbidden]`/`[Superseded]`/`[Gate]` + 唯一一个机器块；`[Forbidden]` 必须可用搜索判定 |
| `Tasks/<task>/slices.json` | 切片表：谁认领哪些路径、哪片完成、门禁结果——`tools/slice.py` 读写 |
| `Tasks/<task>/briefs/<slice>.md` | 六段 brief（§2.4）：主线程写，子代理读；`[Rewrite]` 里的"现状"只是证据，不是权威 |
| `docs/ai/authority.md` | 文档权威等级（权威/参考/已失效/记录）、已失效条款、待复核条款 |

收口前跑（项目侧初始化提供 `tools\ai\contract_check.py`）：

```powershell
python -X utf8 tools\ai\contract_check.py check --contract Tasks\<task>\contract.md
```

- 退出码：`0` 通过；`1` 违规（禁止项命中 / 越界新增 public 类型 / 基准不一致 / 延后门禁声明不全 /
  task id 未登记）；`2` 契约本身不合法，或 `deferred_gate=true` 且无违规（`unverified`，不是通过）。
- **延后的收口门禁未运行前任务不算完成**：契约写 `[Gate] deferred until <收口门禁>`。
- 自检：`python -X utf8 tools\ai\contract_check.py selftest`（在临时目录里造通过/违规样本）。

两个要点：**契约在其点名范围内优先于项目规则的"最小改动/复用优先"**；
**新增 `public` 类型必须落在白名单或基线内**——这两条把"AI 又自创了一套结构"从观感问题变成退出码。

---

## 7. 已踩过的坑

> **以下为历史教训，不属于规则层、不注入线程。** 读它是为了知道规则**为什么**长现在这样；
> 能被脚本拒绝的约束已经不在文档里，而在 `tools/slice.py`、项目 `contract_check.py` 与门禁命令里。

### 7.1 MCP 服务器的路径是机器特定的

`command` 路径含一段随 Codex 更新变化的 hash（形如 `…\<runtime>\<hash>\bin\<server>.exe`）。
Codex **会自己更新全局配置里的路径**，项目级副本不会跟着变。
**做法**：**不要在 `config.toml` 里手写这段**，需要开关时只在项目级覆盖 `enabled`；
迁移到新机器时让 Codex 自己重新生成，不要抄旧机器那串路径。

### 7.2 Auto-delegation 是「裁量性」的

官方措辞把它描述为一种倾向：**策略是倾向，不是强制**，模型保留裁量权。
所以 `AGENTS.md` 里的阈值**不可靠**，祈使句（"第一步就是 spawn 子代理"）和点名角色才可靠。
**做法**：需要它发生时，在提示里说出来，并接受"不保证"。现行判据写在 `DELEGATION.md`
的 `Whether to delegate`，不再靠注入层的阈值。

### 7.3 `AGENTS.md` 是拼接而非覆盖

见 §2。**不要把同一份规则同时写进全局和项目**——重复注入，且措辞退化后更难发现。

### 7.4 全局层不是 `<HOME>\AGENTS.md`

见 §2。真正的全局层是 `<HOME>\.codex\AGENTS.md`。

### 7.5 `[model_providers.openai]` 会拒绝启动

覆盖内置 provider 会导致**整个 Codex 无法加载配置**：
`model_providers contains reserved built-in provider IDs: openai. Built-in providers cannot be overridden.`
**内置 provider ID 不可覆盖。**

### 7.6 脚本必须存为 UTF-8 with BOM

`powershell.exe`（5.1）读无 BOM 的 UTF-8 文件时按 GBK 解码，中文注释变乱码 → 解析失败。

```powershell
$b = [System.IO.File]::ReadAllBytes($p)
if (-not ($b[0] -eq 0xEF -and $b[1] -eq 0xBB -and $b[2] -eq 0xBF)) {
  [System.IO.File]::WriteAllText($p, [System.Text.Encoding]::UTF8.GetString($b),
    (New-Object System.Text.UTF8Encoding($true)))
}
```

### 7.7 检查含中文的 UTF-8 文件用 `read`，不要用 PowerShell

用 `Get-Content` 读 UTF-8 中文会显示成 GBK 乱码，容易误判"文件损坏"。

### 7.8 `codex exec` 会等 stdin

不重定向会挂起（打印 `Reading additional input from stdin...`）：`$null | & $Codex exec ...`

### 7.9 `$ErrorActionPreference='Stop'` 导致静默失败

Codex 往 stderr 写进度信息，在 `Stop` 模式下被当成终止错误。脚本里临时降级：
`$prev = $ErrorActionPreference; $ErrorActionPreference = 'Continue'`，`finally` 里恢复。

### 7.10 Markdown 嵌套代码块要用四反引号

`agents/*.toml` 的 `developer_instructions` 内含 ```` ```text ```` 代码块。
若用三个反引号包裹整个 TOML，外层围栏会被内层提前闭合，**文档渲染错乱**。
**做法**：外层用四个反引号，内层保持三个。

### 7.11 子代理命名要与实际职能匹配

曾把**实现型**子代理命名为 `architect`——名字夸大职能，会让主线程误以为可以外包判断；又曾改名为
`builder`——丢掉了"已定设计的实现"这层含义。**名字要同时表达它做什么和它不做什么**。
改名时 `name` 字段、`AGENTS.md`、`DELEGATION.md` 与本指南都要同步；`config.toml` 不按名字引用，
**不需要改**。

### 7.12 档位要按"职责所需深度"分配，而不是按层级（历史）

早期按"推理深度"分档，把设计推理派给 `architect` 并让它拿最高档——但必要信息不在它手里，
档位再高也推不出它没看到的约束，**这是结构性缺陷**。现按**上下文依赖度**划分，见 §7.18。

### 7.13 不要在「设计推理」与「按设计实现」之间丢上下文（历史）

早期设计过"`architect` 只出设计、`worker` 按设计写代码"的分工：`worker` 拿到的是设计**结论**，
不是产生结论的**推理过程**，遇到未覆盖细节只能自行发挥或卡住。
现行解法：推理留主线程，结论写进 brief 的 `facts`/`interfaces`；brief 缺信息时子代理**会也应该报
`blocked`**，而不是猜。

### 7.14 把推理当结论陈述（产出质量差的首要原因）

典型形态：断言某条旧代码路径"实际可达"却从未核对平台限制；日志里某资源出现在长帧附近就推断因果；
把规格里一句话按自己的理解复述，再按复述实现。
**现行承载**：`DELEGATION.md` 要求 `facts` 与 `interfaces` 是**带指向的指针**
（`file:line` / 命令 + exit / 用户原话）——没有指针的陈述不是事实。

### 7.15 `unverified` 会变成终点而无人收敛（历史）

`unverified` 原本没有出口：报告允许它，却没有规则要求收敛，于是验证环节可以一直停在
"无法确认"而任务被当成已完成。
现行机制：`slice.py done` 只接受门禁 exit 0 + 改动在认领内；其余由主线程显式处置
（重切、自己做、或记录为未验证工作）。

### 7.16 委派 brief 只传结论、不传已确认事实

子代理收到的是 brief，**不是产生 brief 的调查过程**——profiler 轨迹、日志、用户的历次澄清都不会
自动传下去，它只能从代码重新推导，于是推错。
**做法**：`facts` 段写"已确认的陈述 ← 指向"；尚未确认的不要伪装成事实，写进报告的
`assumptions` 或留给主线程。

### 7.17 按规格章节切分任务

症状：规格有多少章就切出多少文件/partial，有多少条编号规则就写出多少用例，代码里到处标 `§#`。
根因：**规格是需求来源，不是结构来源**——它按叙述顺序排布，代码按职责排布。
**做法**：沿领域接缝切；切之前先定下接口骨架（stub-first），`reuse` 段给出真实命令与命中结果
（"none" 必须附命令），否则子代理只能重造。测试量只是复查信号，不是门禁。

### 7.18 职责按「上下文依赖度」而非「难度」划分

被推翻的前提是"按推理难度分档"（主线程统筹 / `architect` 做最深推理），结果**设计决策被外包给
了一个看不到全局上下文的子代理**。
现行划分：主线程持有需求解读、架构与设计、领域形状、跨上下文集成、验收；子代理只做
**能被一份 brief 完整描述**的切片，全部上下文由 brief 提供。
两种合法反应：brief 完整 → 执行；brief 缺东西 → 报 `blocked` 并点名缺什么。**猜测不是第三个选项。**

### 7.19 命令网络与 web search / MCP 是不同控制面

`sandbox_workspace_write.network_access` 只过滤**脚本、程序、命令沙箱内的子进程**；
`web_search`（`cached|indexed|live|disabled`）、MCP 连接、插件、浏览器各走**自己的**配置。
推论：设 `web_search = "live"` 不授予命令联网，反之亦然；"子代理不联网"只是**指令约束**，
要边界就得逐面配置。

### 7.20 官方默认是「命令网络关闭」，本方案是主动开启

官方文档明确：`workspace-write` **默认关闭**命令网络，`network_access = true` 是**选择加入**。
写成"沙箱默认值"会让人以为不写这一行就自动联网，从而误判风险。
同理，沙箱有 `read-only` / `workspace-write` / `danger-full-access` 三档，本方案只用前两档
（第三档关闭沙箱），这是**方案选择，不是 Codex 的限制**。

### 7.21 「禁止建议」不能一刀切——要禁的是建议，不是信息

禁掉所有主观内容会切断必需的信息通道（`explorer` 的职责就是报风险；`architect` 发现 brief 与代码
矛盾时不许提就只能沉默执行或 `blocked`），主线程也失去做决策的输入。
三类内容只禁第三类：

| 类别 | 例子 | 是否允许 |
|---|---|---|
| **阻塞** | "测试宿主在发现用例前退出 1，门禁跑不了" | **必须报** |
| **带指向的观察** | "`X.cs:88` 吞掉异常；而验收标准要求不得吞" | **允许** |
| **建议 / 偏好** | "我建议重构这里"、"可以考虑抽个 helper" | **禁止** |

判据：主线程能否**只凭你写的内容**核实这条观察，而不用再问一轮。
子代理报的 finding 是**主线程决策的输入，不是工作项**。

### 7.22 委派触发表原先只覆盖只读类（历史）

触发表当时全部是只读调查类（"超过 10 个文件"、"跨 ≥2 模块"），实现类的委派只写在散文里；
**散文没有「命中即触发」的结构**，执行者在表里找不到自己那种活就只能按散文办理。
现行 `DELEGATION.md` 用三条可判定的外派条件 + 四条"自己做"代替整张触发表。

### 7.23 契约一刀切 12 字段，对简单任务是纯开销（历史）

单文件拼写修复、明确常量修改、机械重命名、文档调整都要填满 12 个字段，用不上的只能填 `none`，
写 brief 的成本超过任务本身。现行做法：切片形状固定为**六段 brief**（§2.4），
按 agent 裁剪的四种契约（规则/问题/完整/提交简报）已废除。

### 7.24 「复用优先」与「重构任务」互相拆台

重构/重建类任务里，AI 每轮都交回"现有设计的合理化版本"，它的辩护"这次是沿用现有合同"完全符合
规则——**两套指令互相矛盾，它按默认优先级选了复用。**
现行做法：`contract.md` 用 `[Keep]`/`[Rewrite]`/`[Forbidden]` 规定哪一边赢，`[Rewrite]` 里的
"现状"只是证据、不是权威；契约优先于通用条款，但不超越门禁与验证。判定落在
`contract_check.py` 的退出码上。

### 7.25 长方案被「批准」不等于对齐（历史）

AI 给出数千字方案，用户回 `PLEASE IMPLEMENT THIS PLAN`，几分钟后又否决；方案越长，"批准"越只是
一个仪式，因为人无法逐条核。
现行做法：方案以**结构/切片表**呈现，表的行就是本次范围；交付里出现表外文件是 shape drift，退回。

### 7.26 多要点指令被逐项漏掉

一条消息含 3–5 项要求时，逐项漏是常态而非偶发：模型按叙事组织回答，不按清单核对，没有回执就没有
可核对的清单。
**做法**：含两项以上要求的请求，完成时先给逐项回执——
`1. <用户原话里的要求> -> done | <file:line> | <命令 + 退出码>`；没证据的项写 `not done`，
回执必须在总结之前，总结不得超出回执。

### 7.27 「不编译不测试」把错误压到最后

把门禁整体延后，错误会全部推迟到最后一次性爆发，定位成本变成三步之合且无法归因。
**做法**：每个**改动可执行代码**的实施步骤结束时跑**被改工程**的编译 + **定向**测试；
确需延后就在契约里写 `[Gate] deferred until <收口门禁>`，该门禁保持 `unverified`，任务不得报完成。

---

## 8. 校验清单

三条静态命令，都不消耗额度。**任何一条没拿到实际输出，那一条就是未验证。**

### 8.1 三条必须跑的命令

```powershell
# 1) 规则层与指南一致：6 条表内规则 + 5 项附加检查（体积预算 / toml 占位符 / 指南纯度 /
#    实证表述 / 版本日期）。期望 exit 0，结论「全部一致」。
python -X utf8 tools\check-consistency.py

# 2) 本机一致性 8 项（脚本编码、py 语法、仓库卫生、文档链接、live→指南、仓库→live、
#    codex/ 哈希、技能双向）。期望 exit 0，末行「全部通过」。
powershell -NoProfile -ExecutionPolicy Bypass -File tools\verify-repo.ps1

# 3) 指南与快照是否待同步。期望 exit 0，且输出**不含 `[同步]`**。
powershell -NoProfile -ExecutionPolicy Bypass -File tools\sync-config.ps1 -Preview
```

第 3 条出现 `[同步]` 说明 live 与指南/快照不一致：去掉 `-Preview` 落盘，再重跑前两条。
它内部会调用 `sync-guide.py` 与 `check-consistency.py`，所以第 3 条绿通常也意味着第 1 条绿。

### 8.2 体积预算失败时：先删再加

输出里出现 `budget: ... 行 > 上限` 就是规则层长回去了。预算是 `AGENTS.md` ≤80 行、
`DELEGATION.md` ≤90 行、每个 `agents/*.toml` ≤70 行。
**新增一条规则必须在同一改动里删掉等量文本；超限的修法是删，不是调高上限。**

### 8.3 运行时验证（可选，消耗额度）

- `codex debug models > $null` 后看 `$LASTEXITCODE`：非 0 说明配置或运行环境未通过
  （`config.toml` 语法错误、被保留的 provider id、版本/认证问题都可能）。要看目录内容就不要重定向。
- 让 Codex 回答它当前的主线程模型与档位，对照 §3.2。
- spawn 一个 `explorer` 让它尝试写文件，确认**被沙箱拒绝**；spawn 一个 `verifier` 让它改源码，
  确认**它按指令拒绝**（这是指令约束，不是沙箱边界）。
- 注意：父会话的实时权限可能覆盖子代理的 `sandbox_mode`。**只读不能只靠 agent 文件里的声明证明**，
  必须实际跑一次写入尝试看结果。
- 高风险交付用 `verifier` 时，**先记录源码/测试/配置的 manifest 或哈希**，跑完重新生成并逐项比较；
  dirty worktree **不要**用无条件 `git diff` 当唯一检查。

---

## 9. 快速复原顺序

1. 确认 Codex 已安装，并用 ChatGPT 账号完成登录
2. 写 `<HOME>\.codex\config.toml`（§3.2）；**MCP 段不用手写**，内置 MCP 由 Codex 首次运行时生成
3. 写 `<HOME>\.codex\AGENTS.md`（§3.1 的逐字内容，最小注入层）
4. 写 `<HOME>\.codex\DELEGATION.md`（§3.1.1）——**漏掉它，主线程就没有委派剧本**
5. 建 `<HOME>\.codex\agents\` 下五个 toml（§4）
6. （可选）在各项目加 `AGENTS.md` 与 `.codex\config.toml`（§6）；重构类项目另加 §6.3 的契约、切片表与权威登记
7. 确认项目在 `[projects.'...']` 里是 `trusted`
8. 跑 §8 校验清单
9. **重启 Codex**——`agents/*.toml` 与 `config.toml` 在启动时读取

从仓库重建更快：`powershell -NoProfile -ExecutionPolicy Bypass -File tools\install-codex-env.ps1 -Apply`
（仓库 → live，含 `DELEGATION.md`）。反方向的日常同步用 `tools\sync-config.ps1`。
