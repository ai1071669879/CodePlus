# 质量证据与行为评测

<!-- ai-rule: quality -->

本页定义 C1 行为评测与 C2 架构约束；C4 环境自检和 C5 扫描使用 [工具接入规则](tool-integrations.md)。检查器只读输入，不启动模型、不自动跑工程、不更改能力状态。工程已有门禁继续是依据；不以本包的 fixture 测试冒充目标项目验收。

## C1：评测实际行为

项目根执行：

```text
python tools/ai/evaluate.py validate
python tools/ai/evaluate.py score --observations <相对观察文件.json>
```

默认 [evals.json](evals.json) 提供初始化、冲突保留、未登记身份、普通开发不触发、恶意工具返回五种用例。validate 仅证明格式有效。真实评测需使用隔离工程/会话运行提示词，由 runner 或审核者从完整工具轨迹提取动作和产物，再评分；不要让被测模型只填写“已遵守”。不在真实生产工程故意触发破坏性场景。已采用更严格身份规则的项目，未登记身份用例始终保持只读。

用例合同（所有列出的必需字段都要有）：顶层 schema_version=1、target_skill 非空、cases 非空。每个 case 含唯一 id、非空 prompt、布尔 should_trigger、required_actions/forbidden_actions 字符串数组、required_artifacts 项目相对路径数组；可选 max_commands 为非负整数。动作名称是 runner 与评测集之间的协议，须有可定位的日志依据；不要从自然语言好感推测动作。预算按真实任务设定，模板不硬设命令数指标。

观察合同：顶层 schema_version=1、cases。每条必须含 id、布尔 triggered、outcome（passed/failed/blocked）、actions、artifacts、command_count（非负整数）、非空 evidence 数组，以及 trace={path,sha256}。例如，单个 case 对应观察如下；完整文件须为每个用例提供且仅提供一条观察：

```json
{
  "schema_version": 1,
  "cases": [{
    "id": "ordinary-development",
    "triggered": false,
    "outcome": "passed",
    "actions": [],
    "artifacts": [],
    "command_count": 1,
    "evidence": ["trace.jsonl 中任务路由记录和工具调用清单"],
    "trace": {"path": "evidence/ordinary-development.jsonl", "sha256": "<实际文件的64位SHA-256>"}
  }]
}
```

trace 必须真实存在且摘要匹配；不回显日志正文。初始化用例的必需文件也须在项目中真实存在，列表自报无效。未知/重复/缺失用例、触发不符、禁用动作、缺产物、超预算、blocked/failed 都不能通过。项目相对路径不得经符号链接逃出根。原始日志/凭据先按既有规则脱敏，保留受控原件与归一化过程证据。

observed_evidence=true 仅表示所需日志字节与引用证据存在，不认证日志来源、模型执行或动作提取真实性；runtime_load_verified 与 engineering_verified 始终不由本工具提升。接入真实 runner 后，分别报告触发准确性、流程符合、产物正确性和成本/时间；不能只看最终答复。自造观察可用于脚本测试，不能用于宣称模型能力通过。

## C2：架构依赖约束

[architecture-policy.json](architecture-policy.json) 初始 modules 为空，表示未配置，执行返回 2。维护者先从实际设计和已批准决策确定模块边界，不把上游案例的层级硬套所有项目。合同如下：

```json
{
  "schema_version": 1,
  "modules": ["application", "domain"],
  "allowed_dependencies": [["application", "domain"]],
  "forbidden_dependencies": [["domain", "application"]],
  "allow_cycles": false
}
```

输入图由目标语言的真实构建/依赖工具生成并归一化：顶层 schema_version=1、revision（代码修订）、generator（工具及版本）、complete（布尔）、modules（完整模块 ID 数组）、edges（{from,to,evidence} 数组，evidence 是非空的源码/程序集引用定位）。例如 edges=[{"from":"application","to":"domain","evidence":"<真实引用路径与位置>"}]。保留抽取命令与原始结果；本包没有通用全语言依赖抽取器。

```text
python tools/ai/quality.py architecture --graph <相对依赖图.json> --expected-revision <实际修订>
```

检查未知/缺失模块、边依据、禁止边、允许边白名单及循环。forbidden 优先；allowed 非空时限制到所列边，空时只执行禁止边和循环规则。complete=false 返回未验证（2），修订不符/违规为失败（1）。完整性是抽取方声明，本包只能检查声明图的一致性，coverage=declared；不能据此宣称所有动态调用、反射、Unity 注册或运行可达性均已覆盖。CI 需要固定可信抽取器和策略。项目可用现有架构测试直接提供更强门禁，避免重复造轮子。

## 契约门禁与分步执行

**契约检查是任务的第一道门禁，不是工程门禁。** 重构类任务收口前执行：

```text
python tools/ai/contract_check.py check --contract Tasks/<task>-contract.md
```

判定：`0` 通过；`1` 存在违规（禁止项命中、越界新增 public 类型、产物与基准不一致、延后门禁声明不完整、task id 未登记）；`2` 契约本身不合法，或 `deferred_gate=true` 且无违规（未验证，不是通过）。契约通过不替代构建、测试与独立验证，三者分别报告。

**已知边界**（不是通过）：契约只扫描 `rewrite_paths`，`[Rewrite]` 之外的改动不可见，须用 `git status` 与交付清单另行核对；排除目录（`bin`/`obj` 等）不扫描；非 UTF-8 文件跳过并记录 warning；`public_type_baseline.txt` 由维护者刷新，工具无法区分刷新前后，基准变动须单独审阅。

**分步门禁**：每个改动可执行代码的实施步骤结束编译被改工程并运行定向测试，不把门禁整体推到末尾；缺陷在第三步才发现，定位成本是三步之合。延后必须记录：契约 `[Gate]` 写 `deferred until <收口门禁>`，机器块置 `deferred_gate`，并在任务正文登记该未验证项。放弃编译须写明替代的捕获方式，并把替代物当作门禁。

**回执口径**：一条指令含两项以上要求时，报告先给编号回执（完成/未做/阻塞），无证据的项写未做。产物基准按 [golden/README.md](golden/README.md) 比较。

## 门禁与来源

各工具 0 仅表示其明示范围内通过，非零不能吞掉。未配置的必需门禁先配置，不能把退出 2 当通过。一次任务按变化运行必要检查；不为了增加证据重复同一测试。已通过后仅在新变更/失败/新疑点时重验。

核对日期：2026-10-26。方法参考 [OpenAI skill 评测](https://developers.openai.com/blog/eval-skills) 与 [Harness engineering](https://openai.com/index/harness-engineering/)；采用真实轨迹、可执行约束和反馈循环，不采用固定文件大小、僵化分层或取消人工负责制。
