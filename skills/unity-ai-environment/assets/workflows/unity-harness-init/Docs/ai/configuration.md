# 配置合同与管理命令

当前选中 **unity-harness-init**：执行/规划/验收/任务状态按 [workflow.md](workflow.md)。Tasks 字段仅描述保留的原生格式；当前 Tasks/index.json 必须保持空任务表，Harness 状态唯一在 docs/harness/progress.md。

本页是配置字段含义的唯一说明；行为规则由 rules.json 指向的正文定义。路径相对项目根，使用 POSIX 分隔符；本机绝对路径放被忽略的本机文件，不进入共享配置。所有 JSON 的 schema_version 为 1。

## 项目事实 project-profile.json

- project：name、kind、root；root 是环境工作区根的相对路径，当前通常为 `.`。
- commands：build/test/lint 的真实参数数组。空数组表示未配置，空可执行名不是有效命令。检查器不运行这些命令；由 agent 或 CI 使用项目工具和当前权限单独验证。
- generated_paths：生成物的唯一目录/文件来源。权限表不得再维护第二份；旧 policy 同名字段仅警告，不参与生成代码例外。
- conventions.commit_language：目标项目已有的提交说明语言，未确认时留空。先读取项目既有约定，不把某个团队的中文或英文要求强制到所有项目。提交说明须对应最终 diff，明确内容、范围和有证据的验证结论。
- change_controls：可选项目专门确认规则，每条含 id、paths、roles、reason。roles 是适用的操作者角色，空数组适用全部角色；只在角色及路径均命中时提示。迁移时保留既有的特殊实体、共享契约或资源修改确认。它不增加文件权限，scope 不能验证聊天确认；同一明确范围不重复审批。
- verification：平台实际读取规则、CI/服务器强制检查的人工证据状态。静态 check 不把这些值升级为已验证。

### 能力 capabilities

以稳定 id 登记真实工具能力。每项可含 state、skill、source_paths、entrypoints、command、input_kinds、outputs、limitations、verified_revision、evidence。

state 为 unconfigured、located 或 verified：仅找到实现时是 located；verified 必须有非空核验修订和证据。source_paths/entrypoints 是真实相对路径，command 是参数数组，其他列表用字符串。skill 仅记录确实可用的 skill 名；不得把名称当作已安装。输入输出格式、适用平台和能力限制由项目确认。检查器验证结构和引用，不执行技能、导出器、网络请求或构建。

未接入能力保留 unconfigured。不用“我看到了命令/菜单”替代“我运行验证了它”。现有任务可继续做分析和预览，不能虚构保存、导出或运行结果。

## 写入范围 access-policy.json

users 将真实账号映射为已登记 role。所有默认用户与路径为空；登记和更改必须由有权限的维护者执行。roles 提供默认规则；用户同名权限字段分别替换角色字段，不追加。governance 只能来自角色。未知权限字段是错误，避免拼写失误后静默放行。

| 字段 | 含义 |
| --- | --- |
| paths | 普通文件授权；`dir/` 为目录前缀，`**` 为全部，其他按大小写敏感通配符匹配 |
| elevated_paths | 敏感路径的附加授权；还必须满足普通路径或明确的文件授权 |
| denied_paths | 明确拒绝，优先于允许路径 |
| denied_extensions | 禁止的文件类型；`.cs.meta` 按 `.cs` 参与类型检查 |
| file_grants | 附加普通授权，每项含 paths 和 suffixes；后缀按原始文件名精确匹配，例如需要分别列 `.prefab`、`.prefab.meta` |
| code_paths | 可选代码附加范围；字段存在时，policy.code_extensions 所列类型必须同时满足普通授权及此范围；空数组拒绝该类代码 |
| generated_extensions | 对 denied_extensions 的生成文件例外；必须命中 profile.generated_paths，且仍受普通、敏感、治理、所有者与代码范围约束 |
| governance | 角色是否可维护 governance_paths；不自动授予普通路径或敏感权限 |

policy.code_extensions 只指定需附加代码范围检查的类型；通用模板默认空，由目标项目决定。owned_paths 每项含 paths 和 roles：命中内容必须由所列角色承担，不能因有上级目录权限越过归属。角色名必须存在。

匹配文件授权仍不能绕过 deny、文件类型、内容归属、敏感和治理规则。生成代码例外只检验路径/类型，不能证明由正式生成器产生；生成来源仍按工具和交付证据核对。

mode=audit 时报告越界但退出 0，mode=enforce 时越界退出 1；非法路径或无效策略始终失败。两种模式都不是远端认证或文件系统隔离。CI 必须使用可信身份、可信策略与完整变更集。

## 身份与本机缓存

```text
python tools/ai/check_env.py whoami --user <account> --role <declared-role>
python tools/ai/check_env.py identity --user <registered-account> --role <declared-role>
python tools/ai/check_env.py clear-identity
```

whoami 只读；identity 仅缓存已登记用户和自述岗位，clear-identity 仅清除 `.ai-local.json`。身份来源依次为显式账号、AI_PROJECT_USER、本机缓存、与注册表完整匹配的 git user.name。换显式账号不沿用别人的岗位声明；不要从邮箱、历史提交或近似姓名猜账号。

登记岗位与自述岗位不符时 can_edit=false，列出双方及具体冲突；本次任务保持只读，待维护者核实。缓存或手工输入始终 verified=false；可信远端身份由项目集成单独提供。失败的切换不冒充成功，不沿用旧账号授权继续本次写入。

## 导航 context-index.json

entries 每项含 id、aliases、roots、entrypoints、verified_revision。路径必须真实存在，修订需能复查。`context --query` 按 id/别名定向返回条目；未命中先在已知目标目录限定检索，不全仓预读。需要候选清单时在返回的 roots 内使用 `rg --files <module-root>`，再核少量入口和真实调用方。

Git 可解析修订时，check 对目标范围内提交差异、暂存、工作树及未跟踪文件给出 current/stale；缺 Git、修订缺失或浅克隆不可解析时为 unknown。stale/unknown 只提示待复核，不自动改 verified_revision。current 也仅表示本次可观察文件范围未变，不证明运行可达、接口语义或性能仍正确。

## 任务 Tasks/index.json

元数据使用 id、path、status、owner、depends_on。id 唯一，正文必须是真实 Markdown 文件，依赖存在且无循环。owner 非空时须登记；proposed 可未认领。状态为 proposed、ready、in_progress、blocked、review、completed、cancelled，不要求逐个经过中间状态。

可选 source={reference,revision,confirmed_revision}；未确认或变化的修订给 stale 提示，仍允许建候选。可选 approvals=[{by,role,revision,evidence}]、required_approvals=[角色]；审批人须登记且角色一致。候选缺审批仅提示，完成时如配置了所需审批，须有对应当前修订的记录。

completed 必须有 owner 和 acceptance={by,evidence}，by 为该负责人，证据数组非空。source 待确认仍单独提示；是否接受其风险由负责人明确记录。history 追加实际进展，不覆写已有人工记录。字段只能记录人类认领/验收的依据，不证明真的发生了真人操作，也不取代权限与审查。

需求、方案与验收正文采用 task-template.md；已有外部任务系统时明确唯一来源和映射，避免双写状态。

## 规则路由与初始化快照

rules.json 的 sources 将规则 id 指向唯一文档，正文使用对应 ai-rule 定义标记。转读入口不重复正文定义；检查器核对源、唯一标记、所选平台入口及相对链接。实际模型加载另做新会话测试。

`.ai-environment.json` 记录已选择平台、项目种类、受管文件和安装摘要。checker 还从所选平台/项目种类推导必需文件，不能仅靠删除快照条目隐藏缺文件。项目正常定制导致摘要变化仅警告，不自动覆盖。

初始化器的 plan/apply 均可加 `--diff` 查看真实候选内容差异。相同内容幂等；任何冲突整批不写。定制工程升级时逐项比较并人工合并，不删除原配置来绕过冲突。

## 任务契约、文档权威与产物基准

契约的章节、机器块字段与判定口径只在 [task-contract.md](task-contract.md) 说明；文档权威等级与失效条款只在 `authority.md`（authority.md） 登记；产物基准的比较规则只在 `golden/README.md`（golden/README.md） 说明。本节不复制这些正文，只登记文件职责、管理命令与升级关系。

| 文件 | 职责 |
| --- | --- |
| [task-contract.md](task-contract.md) | 契约模板、五个章节与唯一 `json contract` 机器块；单任务契约放 `Tasks/<task>-contract.md`，状态仍只登记 `Tasks/index.json` |
| `authority.md`（authority.md） | 文档权威等级（权威/参考/已失效/记录）、失效日期与替代者、待复核条款 |
| `golden/README.md`（golden/README.md） | 产物基准的登记、比较规则与更新纪律；基准文件放 `Docs/ai/golden/` |
| `Docs/ai/public-type-baseline.txt` | 既有 public 类型清单，一行一个类型名，注释行忽略；用于识别本轮越界新增的类型 |
| `tools/ai/contract_check.py` | 判定器：契约结构、禁止项、`[Rewrite]` 内 public 类型与产物基准 |

契约不是配置项：不写入 `project-profile.json` 或 `access-policy.json`，不改变能力状态，也不新增权限或审批。判定器只读项目树，不执行构建、测试或生成器。

| 子命令 | 用途 | 退出码 |
| --- | --- | --- |
| `check --contract <相对路径>` | 校验章节、机器块、禁止项、`[Rewrite]` 内的 public 类型与 `golden` 比较；`--json` 输出结构化结果 | 0 通过；1 违规；2 契约或参数不合法，或 `deferred_gate` 未验证 |
| `baseline --paths <相对路径>...` | 从工作树提取 public 类型并生成清单；`--out` 写入文件，否则打印到标准输出 | 0 完成；2 参数不合法或源文件不可读 |
| `selftest` | 在临时目录构造通过、违规、基准与延后门禁用例，自检判定器 | 0 自检通过；断言失败非零 |

退出码语义固定为 `0` 通过、`1` 违规、`2` 用法或配置错误以及未验证；`2` 不能当作通过，也不能用解释性输出替代退出码。扫描 public 类型时遇到不可读或不可解码的源文件同样返回 `2`，且不产生部分清单——残缺基线不得伪装成成功。`deferred_gate` 为 `true` 且无其它违规时，`check` 的 status 是 `unverified`、退出码为 `2`，表示延后的收口门禁尚未运行，任务不算完成；`[Gate]` 必须写明 `deferred until <收口门禁>`，不得保留模板占位符。

初始化只复制上述文件；随包的 `public-type-baseline.txt` 仅含两行注释，不含源码类型。初始化后由维护者在项目根显式运行 `python tools/ai/contract_check.py baseline --paths <源码根> --out Docs/ai/public-type-baseline.txt` 生成真实清单；脚本不猜测类型，空清单会把 `[Rewrite]` 范围内的既有类型全部报为 unexpected，因此该项检查以已生成的清单为前提。

升级/重新初始化时仍按整批预检：内容相同的文件保持不变，缺失文件重新创建；已有清单、契约、权威登记或基准与随包内容不同时报告冲突且整批不写，由维护者逐项比较后合并，不覆盖项目已登记的类型、失效日期和基准。删除受管文件后重新 apply 会恢复随包版本；需要保留的项目定制先合并，不用删除后重装绕过冲突。

## 工具接入 integration 与本机路径

capabilities 每项可选 integration 对象，未知字段报错，避免拼写错误静默失效。它复用同一能力 state/evidence，不另建状态表。外部模块默认 enabled=false，version 为空，保持未配置。

| 字段 | 含义 |
| --- | --- |
| enabled / required / writes | 布尔：已选择启用、是否必需、是否声明会写入；不实施隔离或授予权限 |
| provider / group | 工具提供者、互斥组；非空组最多一个启用项 |
| origin / version / license | 官方来源 HTTPS URL、实际固定版本、该版本许可证；不填推测值 |
| transport / endpoint | command、stdio 或 http；endpoint 可空，远程只接受 HTTPS，HTTP 仅限 localhost/127.0.0.1/::1；禁止 userinfo/query/fragment 放凭据 |
| network | 声明允许的主机名数组；不是网络防火墙，不是上传项目的许可 |
| environment_variables | 环境变量名称数组，只记名字、不存值 |
| probe / version_pattern | 明确版本探测 argv；匹配正则可空（空则按 version 文本匹配），不回显原始输出 |
| timeout_seconds | 单次版本探测超时整数，1–30 秒 |

capability.command 仍是实际功能命令的参数数组，probe 是独立的版本探测。空命令/版本表示未配置；HTTP 接入可能无需本地命令，但仍需手工握手证据。doctor 不是通用工具执行器。启用但来源/版本不完整会提示；required 项的可用性由 doctor 检查。

本机 `.ai-local/tools.json` 可用 executables 对象把能力 ID 映射到已选择的绝对可执行文件路径，只替换 argv[0]，不进行 shell 拼接；该文件和身份缓存都必须被忽略。不要把实际个人路径写回 profile 或文档。只读 modules/doctor 和明确的 --probe 见 `tool-integrations.md`（工具接入）；评测与图格式见 [质量流程](quality-workflows.md)，不在本页重复字段。


## 初始化基线与项目适配

`project-baseline.json` 由实际扫描产生，schema_version=1；它是某次静态观察的快照，不替代 profile 当前事实、policy 授权或 context 导航。

| 字段 | 含义 |
| --- | --- |
| project_kind | 使用的环境类型 general/unity；检测到工程不表示自动改变岗位或授权 |
| scan | static-full-inventory；全树遍历范围、受管排除路径、缓存/敏感排除项、问题、文本大小上限、inventory_complete 与始终为 false 的 semantic_complete |
| files | 相对路径、文件分类/语言、字节大小、可读取文本的 SHA-256、content_status；二进制/凭据/超限/不可读内容不伪造摘要 |
| git | 可得的分支、HEAD 与扫描时文件改动；无 Git 标记不可用，不初始化仓库 |
| facts | 检出的语言、依赖/工程清单、Unity根和版本；不是自动安装/运行证据 |
| commands | 声明的 argv、working_directory、purpose、来源路径/行号与 declared 状态；多个/嵌套工程不错误拼成根命令 |
| modules / existing_rules | 真实模块入口及人工已有规则指针，供定向阅读；源码调用链与运行可达另查 |
| adaptations / unresolved | 有来源支持的适配规则和待核实项；规则仍需核读真实来源，未知内容不编造成项目制度 |

快照不存个人绝对路径、原始源码、脚本正文或凭据值，不带会导致重复初始化变化的时间戳。文本白名单内容至多读取1MiB；大型文本标覆盖缺口，二进制仅统计元数据；.git、依赖缓存及 Unity Library 等明确排除，链接不跟随。inventory_complete 仅限声明的盘点范围，semantic_complete 永远不由脚本设为 true。无法读取/解析的清单须报告；扫描完整性不等于业务理解完整。

初始化自动以该快照生成 `project-adaptation.md`，包括适用技术栈/工程约束、已有制度入口、来源依据和待确认项；它在 rules.json 只登记 adaptation 一次。AI 核读原始规则/关键模块后才能完成语义适配：原规则/已登记职责优先，冲突写明条款，任何账号/路径/敏感授权均不从扫描结果推导。只在命令与工作目录有直接证据且唯一时填空的 profile.commands；不覆盖已配置事实或权限。context 的 discovered 入口保持未核验修订，后续实际核对再登记。

`baseline.py scan` 不写文件或启动工程；`compare` 使用已保存扫描范围重新观察并返回 added/removed/changed。相同退出0，变化退出1；无有效基线或扫描不完整退出2。普通 check 只校验结构/预算，不重扫整个工程。更新基线/适配先预览，按当前项目授权由维护者合并；不清空既有状态、负责人和历史。

## AGENTS 的 500 token 预算

限制应用于生成的每个完整 AGENTS.md，包含受管 markers 和人工已有文字。两套核心摘要通过真实 tiktoken 对 cl100k_base 与 o200k_base 核计，`entry-budget.json` 保存 limit=500、精确模板块 SHA-256 与 token_counts；这是声明的两个编码口径，不声称所有模型分词器相同。初始化运行仍只需标准库，不带大型词表或自动下载 tokenizer。

`entry_budget.check_entry` 对精确模板使用已核计数；存在少量人工前后文时，使用模板计数加额外 UTF-8 字节和64的边界余量作保守预算。根入口的初始化与检查启用 require_core：受管核心必须与证书 SHA-256 匹配，报告 core_matches=true；缺少、重复或改写核心均报错，整文很短或刷新 manifest 也不能代替完整性检查。嵌套 Unity 薄入口只检查全文预算，不复制根规则。独立预算函数对未知内容仍可计算 UTF-8 上界，但这个结果不能批准根核心。保守预算不是实际 token 计数。

项目使用不同的文档大小写或路径时，先与完整核心逐项比较，仅适配真实路径与已确认项目约束；详细差异维护在 project-adaptation.md。受管核心发生任何改动，必须审阅全部核心含义，在获准本机用真实 tokenizer 核计包含标记的完整区块，再更新精确哈希和计数；不得仅换哈希、沿用旧数字或手写更短摘要来规避。证书是已审阅内容的快照，不会自动证明新文字没有遗漏。无法证明预算时保留原文并报告冲突，不截断规则；模板变更后跑两包门禁。

根摘要只保留高频决策边界，规则字段和详细流程仍各有唯一正文；摘要与正文冲突属于缺陷，须同时修正并核证据，不靠优先级掩盖。

初始化候选路径与现有人写文件同名，不代表该文件已受管：已有manifest或相同候选内容才可作为受管排除依据；冲突的旧规则仍须进入盘点和已有规则清单，随后整批报告冲突。AGENTS/CLAUDE/.gitignore始终保留人工部分。模块导航包含真实manifest目录，也包含未归属任何manifest目录的源码首级目录，不能因其他子工程有清单而漏掉独立源码。

## 可选目录与当前模式

`setup-options.json` 是静态目录，schema_version=1，tools 每项含 id/name/summary/features/prerequisites/setup；id 必须对应 profile.capabilities，setup 是项目内配方文档路径。它没有 enabled/state/version/evidence，不是第二份能力状态表。

workflows 每项含 id/name/summary/required_tools/state_source/guide。内置 native 无强制外部工具；unity-harness-init 的强制工具集合固定为 unity-skills-rest、unity-harness-init、copilot-cli，不能通过清空目录依赖降级。`workflow.json` 只存 schema_version=1 与 mode（native/unity-harness-init），是模式选择唯一配置。

bootstrap plan/apply 支持 --workflow 与 --tools；省略模式保留既有选择，首次为 native；--tools none 表示不选可选工具。明确工具列表仅改变目录中能力的 enabled，模式必需项另设 enabled/required；不自动改 state、version 或证据，不运行外部工具。互斥组冲突退出2且不写任何文件。不同模式的正文覆盖只在安装事务中选中，切换已有定制须人工合并，不静默覆盖。

`project_setup.py list` 返回选项、当前配置与缺项；check 的0只表示当前已登记前置结构满足，1为无效结构，2为模式强制前置未验证，不把元数据当本次在线会话。`context.py` 复用既有索引按多个ID/别名或路径定向选择；只读输出必要入口、导航时效与声明的not_run门禁，不创建新索引、执行构建或证明实际加载。

字段中的 Tasks 状态适用于 native；Harness 模式状态唯一在 docs/harness/progress.md，Tasks/index.json 保持空任务表，其余 Tasks Markdown只作接力。运行时配置和宿主实际加载分别取证。
