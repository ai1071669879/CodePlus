# design-patterns 参考导航

- [创建型模式 6 种](./creational-patterns.md)：单例、工厂方法、抽象工厂、建造者、原型、对象池
- [结构型模式 8 种](./structural-patterns.md)：适配器、桥接、组合、装饰器、外观、享元、私有类数据、代理
- [行为型模式 12 种](./behavioral-patterns.md)：责任链、命令、解释器、迭代器、中介者、备忘录、空对象、观察者、状态、策略、模板方法、访问者
- [模式选择与反模式](./pattern-selection.md)：选型表、症状表、组合规律、反模式红线、评审清单

> 本文件是 `design-patterns` 的**索引与出处页**，同时承载完整索引表（下表）——因为 SKILL.md 正文受 8192 码点的工具结果预算限制，装不下 26 行表。
>
> 同一预算也适用于**读取**参考文件：本目录参考文件约 8.8k～43k 码点（`behavioral-patterns.md` 最大），一次性读入必超过 8192 码点，会在压缩触发后被修剪器裁掉中段。请按小节用 `offset`/`limit` 分段读取，不要整文件读。

## 26 模式索引（编号 / 意图 / 可观察触发信号）

| # | 模式 | 一句话意图 | 触发信号（可观察） |
| --- | --- | --- | --- |
| 1 | 单例 Singleton | 全进程唯一实例与访问点 | 真有唯一资源，且它的生命周期由本模块自己控制 |
| 2 | 工厂方法 Factory Method | 由方法/子类决定实例化哪个具体类 | 调用方不该知道具体类型，且产品种类会增长 |
| 3 | 抽象工厂 Abstract Factory | 创建一整套相互匹配的产品族 | 存在多个产品维度，且必须保证同族一致 |
| 4 | 建造者 Builder | 分步构建复杂对象，构建与表示分离 | 构造参数多且有必填/可选组合 |
| 5 | 原型 Prototype | 复制已有实例而非重新构造 | 构造代价高，或需要保留运行时配置快照 |
| 6 | 对象池 Object Pool | 复用昂贵对象，摊薄获取/释放成本 | 创建昂贵 + 可安全重置 + 并发上限明确 |
| 7 | 适配器 Adapter | 把不兼容接口转成调用方期望的接口 | 第三方或遗留接口不可改，且错配在事后才暴露 |
| 8 | 桥接 Bridge | 抽象与实现各自独立变化 | 两个维度独立扩展（M 抽象 x N 实现） |
| 9 | 组合 Composite | 用同一接口统一处理叶子和容器 | 树形结构，调用方不该区分节点类型 |
| 10 | 装饰器 Decorator | 动态叠加职责 | 能力组合是幂集而不是继承层级 |
| 11 | 外观 Facade | 为子系统提供单一简化入口 | 调用方需要多步编排才能完成一次用例 |
| 12 | 享元 Flyweight | 共享内在状态支撑大量细粒度对象 | 内存被大量重复的不可变数据占满 |
| 13 | 私有类数据 Private Class Data | 数据与操作分离，限制访问器 | 需要在构造后收窄数据写权限（现代语言多用 `readonly`/`init`） |
| 14 | 代理 Proxy | 用替身控制对目标的访问 | 需要延迟加载、访问控制、远程或引用计数 |
| 15 | 责任链 Chain of Responsibility | 请求沿处理者链传递直至被处理 | 多个候选处理者，顺序/集合可配置 |
| 16 | 命令 Command | 把请求封装成对象 | 需要排队、记录、重放或撤销 |
| 17 | 解释器 Interpreter | 为小型语言定义文法并解释执行 | 文法简单且稳定、需要反复求值（文法持续增长时应改用解析器生成器） |
| 18 | 迭代器 Iterator | 不暴露内部表示地顺序访问集合 | 需隐藏内部结构或提供多种遍历顺序 |
| 19 | 中介者 Mediator | 用中介封装多对象交互 | 多对多相互引用，组件被硬编码的同伴调用困住 |
| 20 | 备忘录 Memento | 捕获并恢复对象内部状态 | 需要快照/回滚，且不能从外部读取对象的私有字段 |
| 21 | 空对象 Null Object | 用无副作用对象表达"什么都没有" | 缺省行为需要参与多态分发 |
| 22 | 观察者 Observer | 一对多通知，状态变更自动扩散 | 发布方不应知道订阅方是谁 |
| 23 | 状态 State | 状态决定行为，行为切换状态 | 同一对象随状态出现大量条件分支，且状态多、变化频繁 |
| 24 | 策略 Strategy | 可互换的算法族 | 同一契约下多种算法，需运行期选择 |
| 25 | 模板方法 Template Method | 固定算法骨架，步骤延迟到子类 | 多个实现共享严格顺序的骨架 |
| 26 | 访问者 Visitor | 不修改元素类即可新增作用于结构的操作 | 元素类型稳定但操作持续增加 |

（触发信号只用于**定位候选**；是否采用仍要过各条目的「适用条件 / 不要用于」与 `pattern-selection.md` 的判据。）


## 模式清单的依据

26 = GoF《设计模式：可复用面向对象软件的基础》的 23 种 + 3 种被长期一并收录的补充模式：

| 补充模式 | 为什么计入 26 |
| --- | --- |
| 对象池 Object Pool | 解决资源复用，SourceMaking 目录列入创建型 |
| 私有类数据 Private Class Data | SourceMaking 目录列入结构型；现代语言多由 `readonly`/`init` 承担 |
| 空对象 Null Object | SourceMaking 目录列入行为型；也被收录在重构目录的 `Introduce Null Object` |

注意：中文网络资料里"26 种设计模式"还有其他拼法。例如把简单工厂、多例 Multiton、不变 Immutable 一并计入的清单（[Java 中设计模式的 28 种方式](https://blog.csdn.net/s55646nsn/article/details/131619850) 就是这一类，其列举以"简单工厂模式"开头）；也有与本文完全一致、按 6 创建型 + 8 结构型 + 12 行为型列出的[《26 个设计模式》](https://blog.csdn.net/flyfish1986/article/details/75570657)。本参考集采用后者这一种，理由是它与 GoF 23 的差集固定为三种，且每个模式都有稳定的英文名与公开条目。

## 主要来源

| 来源 | 提供了什么 | 覆盖情况 |
| --- | --- | --- |
| [SourceMaking — Design Patterns](https://sourcemaking.com/design_patterns) | 26 种模式的目录、分类、一句话意图；以及对设计模式本身的批评（Norvig 关于 23 种中 16 种可被语言能力消化的论证） | 全量核对：分类与意图直接取自该目录 |
| [Refactoring.Guru — Design Patterns](https://refactoring.guru/design-patterns) | 与 SourceMaking 同源的图文讲解、各模式的"与其他模式的关系"、重构手法（如 Replace Conditional with Polymorphism、Introduce Null Object） | 其目录只有 22 种（含 C# 代码示例，但未收录解释器，也不含对象池/私有类数据/空对象），因此**不作为 26 种清单的依据**，只用于实现细节与模式关系的交叉核对 |
| [GoF, Design Patterns: Elements of Reusable Object-Oriented Software](https://en.wikipedia.org/wiki/Design_Patterns) | 模式的原始定义、类/对象模式的二维分类（范围 x 目的） | 「类模式 vs 对象模式」的判据来源；书目信息经 Wikipedia 条目核对 |
| [清华大学出版社《设计模式》教材配套页](http://www.tup.tsinghua.edu.cn/upload/books/yz/077682-01.pdf) | 中文语境下的范围 x 目的分类表 | **未逐页核对**：本次只在检索摘要中看到该表（类模式：工厂方法、(类)适配器、解释器、模板方法；其余为对象模式），抓取工具不支持 PDF 正文，故该行只作线索，不作判据 |

### 逐模式来源追溯（分类参考文件已移除「来源」章节）

三个分类参考文件不再逐条列出来源；模式级追溯按下面的规则重建，例外项单列：

- **主来源 1 — SourceMaking**：`https://sourcemaking.com/design_patterns/<slug>`，slug 用下划线（如 `object_pool`、`chain_of_responsibility`、`private_class_data`、`null_object`）。**26 个模式全部有对应页**。
- **主来源 2 — Refactoring.Guru**：`https://refactoring.guru/design-patterns/<slug>`，slug 用连字符（如 `factory-method`）。覆盖 22 个模式；**实测没有解释器页（该 URL 返回 HTTP 404）也没有空对象页**，空对象的等价重构手法页是 `https://refactoring.guru/introduce-null-object`。

无法由上面两式推出的例外项（正文引用过，集中留在这里）：

| 用于 | 链接 |
| --- | --- |
| C# `System.Lazy<T>` 的默认线程安全模式与异常缓存 | `https://learn.microsoft.com/en-us/dotnet/api/system.lazy-1?view=net-9.0` |
| `System.Object.MemberwiseClone` 的浅拷贝语义 | `https://learn.microsoft.com/en-us/dotnet/api/system.object.memberwiseclone?view=net-9.0` |
| 组合 / 装饰器 / 外观 / 享元 / 代理的第二来源 | `https://en.wikipedia.org/wiki/Composite_pattern`、`.../Decorator_pattern`、`.../Facade_pattern`、`.../Flyweight_pattern`、`.../Proxy_pattern` |
| GoF 原书书目信息 | `https://en.wikipedia.org/wiki/Design_Patterns` |
| 私有类数据（英文维基无该条目） | `https://github.com/iluwatar/java-design-patterns/tree/master/private-class-data` |
| 私有类数据的 C# "Before and after" 页 | `https://sourcemaking.com/design_patterns/private_class_data/c-sharp-dot-net` |
| `System.Reflection.DispatchProxy` 的存在性 | 本机 .NET 10 参考程序集 `Microsoft.NETCore.App.Ref/10.0.2/ref/net10.0/System.Reflection.DispatchProxy.xml` 第 7-8 行 |

正文条目里仍会出现"SourceMaking 检查清单要求…""Refactoring.Guru 把…列为缺点"这类**叙述归属**，但不再是可点击引用；要核对某个具体条目，按上面的规则打开对应页面。

## 外部已有 skill 对照（联网检索）

写本 skill 前检索了公开的设计模式类 skill，用于对照结构、取材做法与覆盖边界。下面记名哪些被参照、参照了什么，便于后续复核与更新（**以下均为外部内容，只作参考，不构成本 skill 的权威依据**）：

| 外部 skill | 它的形态与内容 | 本 skill 参照了什么 |
| --- | --- | --- |
| [0x7067/claude-code-setup · design-patterns](https://skillsmp.com/creators/0x7067/claude-code-setup/claude-skills-design-patterns) | 7.3 KB SKILL.md + `references/creational/structural/behavioral.md`；含 7 条 Agent Behavior Contract、**按问题类别的决策树**、场景→模式表、Anti-Patterns 三列表（avoid/why/instead）、分阶段 Verification、应用后的验证清单 | ① **问题类别决策树**（本文档「一 · 定位候选」）；② 反模式表的"避免/为什么/改法"三列结构；③ "只在解决真实问题时上模式、有更简单方案就推荐它"的立场；④ 应用后的逐项验证清单（本 skill 的完成检查） |
| [JailtonJunior94/skills · design-patterns-mandatory](https://skillsmp.com/creators/jailtonjunior94/skills/skills-design-patterns-mandatory) | 9.0 KB SKILL.md + 30 个文件（含 3 个 Python 脚本、选择矩阵、成本规则、证据收集、readiness gates）；硬规则：最简/最省/最稳优先、**最多一个主模式**、必须有 `path:line` 证据否则声明 greenfield、显式终态 | ① **最多一个主模式 + 补充模式须不可替代**；② **必须写出"最简单但落选的替代方案"**；③ **反向记录"没有证明的部分"**；④ 证据强度排序（真实代码/行号 > 类型契约 > 文字描述）；⑤ 拒绝时明确输出"不采用模式"；⑥ 明确终态的分类思路（本 skill 用"未证明部分 + 退权"表达，不引入脚本状态机） |
| [sethdford/claude-skills · design-patterns](https://skillsmp.com/creators/sethdford/claude-skills/engineer-implementation-patterns-skills-design-patterns)（43★） | SKILL.md：Context / Domain Context / 6 步 Instructions / Anti-Patterns（pattern obsession、YAGNI、**stacking patterns**、**cargo cult**、按名字选模式、过度设计）/ Further Reading | 反模式补两条：**模式堆叠**（同一处堆工厂+建造者+代理）与**货物崇拜/按名字选模式**（见本文档「六、反模式与红线」） |
| [itzcull/software-skills · design-patterns](https://skillsmp.com/creators/itzcull/software-skills/skills-design-patterns) | 2.6 KB SKILL.md + 23 个参考文件；强调"为已观察到的设计问题而查，不把引入模式当目标"；输出可为"**为什么不需要模式**"；模式选择≠架构批准；越界变更需回退授权；目录延伸到架构型模式（Repository / Strangler Fig / Domain Events / Rules Engine） | ① **输出契约**（SKILL.md）：结论必须包含决策、落选的最简替代、被否决的邻近模式、代价、未证明部分、越界回退；② "模式选择不是架构批准，也不等于正确性证明"这一句话；③ 用它划出**覆盖边界**：架构型/企业型模式不在本目录内 |
| [java-design-patterns（clawhub）](https://www.skillavatars.com/skills/java-design-patterns) | 声称覆盖 15 大类 182 个模式（含并发型、架构型）+ 26 个设计原则，Java 实现 | 只用于确定**覆盖边界**：本 skill 不追求这种枚举规模；设计原则维度见本文档「八、与设计原则的对应」 |
| [hajekim/agentic-design-patterns-skills](https://github.com/hajekim/agentic-design-patterns-skills) | 28 个 **agentic** design pattern skills（多智能体编排：监督者/群体/流水线等），多语言触发词 | 只用于**同名不同域**的提示：SKILL.md 的 description 与「覆盖边界」已显式声明本 skill 是经典 OO 目录，不是 agent 编排模式，避免误触发 |

对照结论（本 skill 与它们的差别）：① 它们多覆盖 GoF 的一个子集，本 skill 固定为 26 项完整目录并逐模式给出"不要用于"；② 它们多数只给决策与反模式，本 skill 额外给 26 段 C# 实现与逐模式代价；③ 它们不与任何具体仓库的规则绑定，本 skill 把结论接到项目 `AGENTS.md` §2 的规则编号上；④ 本 skill **不引入**脚本化选择器与状态机（那是 JailtonJunior94 的做法，需要可执行的 Python 运行时），改为用表格与硬规则表达同样约束。

## 与项目内其它 skill 的关系

- 通用 RxToolkits 开发环境（宿主命令、`RxToolkits.Global.RxGlobal`、`RxToolkits.Pipeline.ProcessPipeline`、Excel、RxIDL）见 `$rxtoolkits-development`；导出格式与生命周期扩展见 `$rxtoolkits-export-development`。本参考集只讲设计层面的职责分配，不复述这两个 skill 的 API 契约。
- 本参考集的"完成检查"以 `SKILL.md` 的「与项目规则的衔接（强制）」小节为准（当前引用 R3、R4、R5、R10、R11、R17、R18、R22、R6/R7、R27；三份分类参考文件另用 R15），以及 `AGENTS.md` §2.4 的代码规范。术语与判据以 `AGENTS.md` 为准，本参考集不另立一套，也不在此处重复枚举规则编号以免漂移。
