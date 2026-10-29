# 任务意图契约

<!-- 本文件是模板与判定口径，不是某个任务的契约。单次任务的契约放在 `Tasks/<task>-contract.md`，并在 `Tasks/index.json` 登记。 -->

## 为什么需要它

本项目规则要求「先理解、查找并复用」「优先最小兼容改动」，旧规格文档（旧规格文档）与现状代码也默认是权威。**重构类任务的要求与此相反**：被推翻的那部分现状只是证据，不是权威。两条规则同时生效时，实现会自然回到旧设计，并引用「现有合同」自我辩护——这不是理解错误，是规则冲突。

契约的作用只有一个：**规定这一轮哪些部分沿用、哪些部分推翻**，并给出可机器判定的边界。契约在其点名范围内**优先于** `project-rules.md` 的通用条款；契约没有规定且影响实现的冲突，属于阻塞问题，必须先问，不自行裁决。

## 何时必须写

必须写：重构、重建、替换既有设计、跨模块职责调整、迁移到新框架、修改被旧规格文档描述的既有约定。

不必写：局部缺陷修复、命名/格式调整、有既有测试覆盖的小范围实现、文档修订。判断标准是「本轮是否推翻某项既有约定」，不是改动行数。

## 五个章节

正文用中文说明判定，每节写**可被第三人复核的条款**，不写流程叙述。

- `[Keep]`：保持权威的既有合同。复用优先在此照常生效。写明具体路径/类型/文档条款。
- `[Rewrite]`：当前形态只是证据的路径、类型与文档。注明「现有代码如此」不能作为设计依据；注明替换后的目标形态归属哪个模块。
- `[Forbidden]`：不得出现的名字、结构、机制。每项都要能被搜索或静态检查判定，并写明否决理由（来自哪一轮裁决）。
- `[Superseded]`：已失效的文档与条款，附失效日期与替代者。可读作历史，不得按其实现。
- `[Gate]`：收口门禁命令与期望退出码；延后门禁时必须写 `deferred until <收口门禁>`。

## 机器块

契约正文后追加**唯一一个** `json contract` 代码块，供 [contract_check.py](../../tools/ai/contract_check.py) 判定：

| 字段 | 必填 | 作用 |
| --- | --- | --- |
| `schema_version` | 是 | 固定 `1` |
| `task` | 是 | 任务标识，与 `Tasks/index.json` 的 `id` 一致 |
| `rewrite_paths` | 是 | 本轮允许重写的仓库相对路径；新建路径写 `new:<path>` |
| `keep_paths` | 否 | 禁止检查时跳过的路径（与 `[Keep]` 对应） |
| `forbidden` | 否 | `[{pattern, reason}]`，`pattern` 是正则，命中即违规 |
| `allowed_new_public_types` | 否 | 本轮允许新增的 `public` 类型名 |
| `public_type_baseline` | 否 | 既有 public 类型清单文件，一行一个类型名 |
| `golden` | 否 | `[{path, golden, optional}]`，产物与基准逐行比较（忽略行尾空白与换行风格） |
| `deferred_gate` | 否 | 门禁延后时置 `true`，检查结果为 `unverified` |

`allowed_new_public_types` 与 `public_type_baseline` 共同回答「这轮是否又自创了类型」：`[Rewrite]` 范围内出现的每个 `public` 类型，必须落在两者之一，否则违规。首次使用或既有类型变化后，由维护者显式刷新基线，再执行检查：

```text
python tools/ai/contract_check.py baseline --paths <模块根> <模块根> --out Docs/ai/public-type-baseline.txt
python tools/ai/contract_check.py check --contract Tasks/<task>-contract.md
```

退出码：`0` 通过；`1` 违规（含 `task` 未在 `Tasks/index.json` 登记）；`2` 契约本身不合法、public 类型扫描遇到不可读/不可解码的源文件（拒绝生成部分基线），或 `deferred_gate=true` 且无违规——**未验证不是通过**，延后的收口门禁未运行前任务不算完成。**契约检查是任务的第一道门禁，不替代构建、测试与独立验证。**

已知边界（工具不判定，须人工核对）：只扫描 `rewrite_paths`，`[Rewrite]` 之外的改动不可见，用 `git status` 与交付清单核对改动集；`bin`/`obj` 等排除目录不扫描；`[Rewrite]` 范围内 public 类型扫描遇到不可读或不可解码的 `.cs` 直接返回 `2`，禁止用部分扫描结果生成基线；禁止项扫描遇到不可读文件只记 warning；`keep_paths` 不得与 `rewrite_paths` 重叠（重叠即契约错误）；`public_type_baseline.txt` 由维护者刷新，工具无法区分刷新前后，基准变动须单独审阅。

## 模板

````markdown
# 契约：<任务标题>

## 元信息

- 任务 id：<与 Tasks/index.json 一致>
- 现行基线：分支 <branch>，HEAD <sha>，已有改动 <count> 个文件已保留
- 契约优先级：本文件在下列点名范围内优先于 project-rules 的通用条款

## [Keep]

- <路径/类型/文档条款>：保持不变，复用优先照常生效

## [Rewrite]

- `<path>`：当前形态仅作证据；目标形态归属 `<module>`，<一句话目标>

## [Forbidden]

| 模式 | 判定 | 理由 |
| --- | --- | --- |
| `<regex>` | 搜索命中即违规 | <来自哪一轮裁决> |

## [Superseded]

- `<doc> §<section>`：自 <YYYY-MM-DD> 起失效，替代者为 <path/条款>

## [Gate]

- 收口门禁：`<command>`，期望 exit 0，决定性输出行：`<line>`
- 独立验证：`<command>`（高风险时必填）
- 延后门禁：<无 / deferred until `<closing gate>`>

```json contract
{
  "schema_version": 1,
  "task": "<task-id>",
  "rewrite_paths": ["<模块根>"],
  "keep_paths": ["<保持不变路径>"],
  "forbidden": [
    {"pattern": "<禁用词>", "reason": "<第几轮裁决>"}
  ],
  "allowed_new_public_types": [],
  "public_type_baseline": "docs/ai/public-type-baseline.txt",
  "golden": [
    {"path": "<本轮产物路径>", "golden": "<目标名>.example", "optional": true}
  ],
  "deferred_gate": false
}
```
````

## 与交付的关系

交付报告写明：满足的契约块、`contract_check.py` 的退出码与决定性输出、未覆盖的 `[Rewrite]` 项及其原因。三项缺一项即视为交付未验证。契约结论不由执行者自行扩张：`[Rewrite]` 之外的改动属于越界，回退或另开任务。

契约不超越提交授权、凭据处理与验证等级：`[Rewrite]` 只决定允许改什么，不决定要验证多少；高风险改动仍按 project-rules 的验证风险表独立验证，提交仍走提交门禁。

文档权威等级与已失效条款登记见 [authority.md](authority.md)；产物基准样例登记见 [golden/README.md](golden/README.md)。
