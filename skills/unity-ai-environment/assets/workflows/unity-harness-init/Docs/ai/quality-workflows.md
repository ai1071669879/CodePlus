# 质量证据与行为评测

<!-- ai-rule: quality -->

本页定义 C1 行为评测与 C2 架构约束；C4 环境自检和 C5 扫描使用 `tool-integrations.md`（工具接入规则）。检查器只读输入，不启动模型、不自动跑工程、不更改能力状态。工程已有门禁继续是依据；不以本包的 fixture 测试冒充目标项目验收。

## C1：评测实际行为

项目根执行：

```text
python tools/ai/evaluate.py validate
python tools/ai/evaluate.py score --observations <相对观察文件.json>
```

默认 `evals.json`（evals.json） 提供初始化、冲突保留、未登记身份、普通开发不触发、恶意工具返回五种用例。validate 仅证明格式有效。真实评测需使用隔离工程/会话运行提示词，由 runner 或审核者从完整工具轨迹提取动作和产物，再评分；不要让被测模型只填写“已遵守”。不在真实生产工程故意触发破坏性场景。已采用更严格身份规则的项目，未登记身份用例始终保持只读。

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

`architecture-policy.json`（architecture-policy.json） 初始 modules 为空，表示未配置，执行返回 2。维护者先从实际设计和已批准决策确定模块边界，不把上游案例的层级硬套所有项目。合同如下：

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

## Harness 的主验收与辅助工具

本页 C1/C2 仅作为按合同选用的辅助证据工具；Harness 的主执行/评审由 [workflow.md](workflow.md) 规定，必须通过 Unity Skills REST 并使用独立的不同模型系列 Reviewer。原生 contract_check 前置与按风险免建档流程已停用，只有合同明确引用才附加。

辅助脚本退出 0 不替代真实 REST 编译/测试/日志/场景验证。保留原始报告和未运行项，不自动修改状态。
