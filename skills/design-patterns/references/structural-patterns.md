# 结构型模式 (Structural Patterns)

## 概览

结构型模式解决同一类问题：在尽量不改动已有类型源码的前提下，通过包装、委托、组合与共享，把若干类与对象装配出新的能力。它们不引入新算法，只改变"谁调用谁、谁持有谁"——把原本编译期写死在类里的关系挪到运行期的对象图上，新增能力因此不再需要修改被扩展的类。代价也统一来自这一点：每种模式都会增加一层间接（多一个类型、多一次转发、多一处需要同时理解的双方），所以判据不是"这里能不能套模式"，而是"这一层间接是否真的买到了独立变化的能力"。以下 8 个模式按 SourceMaking 结构型目录的顺序排列。

| # | 模式 | 一句话意图 | 最关键的代价/风险 |
| --- | --- | --- | --- |
| 1 | 适配器模式 (Adapter) | 把已有类的接口转换成调用方期望的接口，让原本不兼容的双方协作 | 多出一层转换类型；若被适配方本可修改，直接改它往往比适配更简单 |
| 2 | 桥接模式 (Bridge) | 把抽象与实现拆成两条可各自演化的层次，避免类的组合爆炸 | 把高内聚的类硬拆成两半会让代码更难懂；只有一种实现时属于过度设计 |
| 3 | 组合模式 (Composite) | 用统一接口同时表示单个对象与对象组合（整体-部分树） | 为"透明"把子节点管理提到组件接口，叶子被迫提供无意义的增删 |
| 4 | 装饰器模式 (Decorator) | 在运行期给单个对象叠加职责，替代子类组合爆炸 | 层层包装后对象身份被隐藏、调试栈不可读；叠放顺序成为隐含约束 |
| 5 | 外观模式 (Facade) | 为复杂子系统提供一个统一、简化、更高层的入口 | 成为唯一入口会限制高级用法；持续加料会喂成"上帝对象" |
| 6 | 享元模式 (Flyweight) | 共享内在状态、把外在状态外置，支撑海量细粒度对象 | 客户端被迫承担外在状态；共享对象一旦可变就会全局串味 |
| 7 | 私有类数据模式 (Private Class Data) | 把数据从使用它的方法中剥离成独立数据对象，收窄写权限 | 现代 C# 的 `readonly` / `init` / `record` 已覆盖大部分目标，常只剩样板 |
| 8 | 代理模式 (Proxy) | 用同接口的替身控制对真实对象的访问 | 每次调用多一次转发；代理里塞业务逻辑会成为隐藏的第二个实现 |

---

## 1. 适配器模式 (Adapter)

**意图**：把一个类的接口转换成客户端期望的另一个接口，使原本因接口不兼容而无法协作的类可以一起工作。SourceMaking 原文为 "Convert the interface of a class into another interface clients expect"，Refactoring.Guru 表述为让接口不兼容的对象能够协作。

**适用条件**（可观察的前置条件）：
- 存在一个"能用但不能直接调"的已有类型（第三方库、遗留代码、依赖众多的类），且你无法或不应修改其源码。
- 调用方已按另一个接口编写，双方在接口形态或数据形状上不一致（返回整行数组 vs 要求按行读取、上左+下右 vs 起点+宽高）。
- 不兼容点是"接口或数据形状"而不是"缺少某项职责"（后者属于装饰器），且错配属于事后集成——系统成型后才暴露。

**不要用于**：可以（也应当）直接修改被适配方的源码、或把双方统一到同一个接口时——直接改服务类往往比多一层适配更简单；不兼容点其实是"缺少某项职责"而非"接口或数据形状"时（后者属于装饰器）。

**角色**：Client（按目标接口编写的调用方）；Client Interface（调用方期望的目标接口）；Adaptee/Service（已有的、接口不兼容的组件）；Adapter（实现目标接口、持有 Adaptee，把调用翻译过去）。对象适配器用组合；C# 没有多继承，"类适配器"只能用"继承 Adaptee + 显式实现目标接口"近似。

**C# 最小实现**：

```csharp
namespace DesignPatterns.Samples.Structural;

// Client Interface：调用方已经依赖的目标接口
public interface IReportSource
{
    System.Collections.Generic.IReadOnlyList<System.String> ReadLines();
}

// Adaptee：已有、不希望改动的组件，接口与目标接口不兼容
public class LegacyCsvReader
{
    public System.String[] ReadAllRecords() => ["region,amount", "east,120"];
}

// 对象适配器：组合 Adaptee 并翻译调用；C# 无多继承，类适配器只能「继承 + 显式接口实现」
public sealed class CsvReportSourceAdapter : IReportSource
{
    private readonly LegacyCsvReader _reader;
    public CsvReportSourceAdapter(LegacyCsvReader reader) => _reader = reader;
    public System.Collections.Generic.IReadOnlyList<System.String> ReadLines() => _reader.ReadAllRecords();
}

public sealed class LegacyCsvReaderAdapter : LegacyCsvReader, IReportSource
{
    System.Collections.Generic.IReadOnlyList<System.String> IReportSource.ReadLines() => ReadAllRecords();
}
```

**代价与误用信号**：
- 类型与接口数量增加、整体复杂度上升；Refactoring.Guru 的 Cons 明确写了这一点，并提醒"有时直接改服务类让它与其余代码一致会更简单"。
- 误用信号：适配器里出现业务规则（校验、汇总、补默认值），或同一对被适配双方出现多个适配器并各自重复同一段转换逻辑——转换逻辑应只存在一处，业务规则属于调用方或被适配方。
- 误用信号：被适配方本可修改却选择适配，两套接口长期并存，"哪套是权威接口"永久含糊。

**易混辨析**：与装饰器的区别在于适配器改变接口（提供不同视图），装饰器保持接口不变只增强职责，因此只有装饰器支持递归叠层；与代理的区别在于代理与被代理对象实现同一接口，客户端分辨不出替身；与外观的区别在于外观为整个子系统定义更简单的新接口、通常包裹多个对象，适配器让既有接口变得可用、通常对应一个被适配方（SourceMaking 特别提醒：包裹对象数量不是判据，意图才是）。

---

## 2. 桥接模式 (Bridge)

**意图**：把抽象与实现解耦，使两者可以独立变化。SourceMaking 表述为"在继承层次里发布接口、在另一条继承层次里埋藏实现"，Refactoring.Guru 表述为把一个庞大的类或一组紧密相关的类拆成两条可各自开发的层次（abstraction 与 implementation）；其典型动机是"M 种调度器 × N 种平台"会退化成 M×N 个类。

**适用条件**（可观察的前置条件）：
- 领域里能明确指出两个正交（互不依赖）的扩展维度，任一维度新增取值都不应要求另一维度跟着增加类型。
- 类数量正在按乘法增长，或能观察到"为组合两个维度而不断新建子类"的历史提交。
- 需要在运行期替换实现，且层次划分发生在设计期——SourceMaking 认为桥接是"让它们在设计出来之前就能协作"，与事后补救的适配器相对。

**不要用于**：只有一个扩展维度、另一种取值用策略或直接实现就能表达时；拆出的两侧不会各自独立演化（两条层次的方法几乎一一对应、只是换了名字）时。

**角色**：Abstraction（高层控制逻辑，持有 Implementation 引用并委托低层工作）；Refined Abstraction（抽象维度的变体）；Implementation（声明所有具体实现共用的最小原语接口）；Concrete Implementation（平台相关实现）；Client（负责把抽象对象与某个实现对象接起来）。

**C# 最小实现**：

```csharp
namespace DesignPatterns.Samples.Structural;

// Implementation：只声明平台相关的最小原语
public interface IExportSink
{
    void WriteLine(System.String payload);
}

// 持有 StreamWriter，所有权与释放责任写进类型契约（R22）：调用方用 using 或显式 Dispose
public sealed class FileSink(System.String path) : IExportSink, System.IDisposable
{
    private readonly System.IO.StreamWriter _writer = new(path);
    public void WriteLine(System.String payload) => _writer.WriteLine(payload);
    public void Dispose() => _writer.Dispose();
}

// Abstraction：高层逻辑只依赖 IExportSink，实现由构造函数注入
public abstract class Exporter(IExportSink sink)
{
    protected IExportSink Sink { get; } = sink;
    public abstract void Export(System.Collections.Generic.IReadOnlyList<System.String> rows);
}

// Refined Abstraction：抽象维度独立扩展，实现维度不需要改动
public sealed class HeaderFirstExporter(IExportSink sink, System.String header) : Exporter(sink)
{
    public override void Export(System.Collections.Generic.IReadOnlyList<System.String> rows)
    {
        Sink.WriteLine(header);
        foreach (System.String row in rows) { Sink.WriteLine(row); }
    }
}
```

**代价与误用信号**：
- Refactoring.Guru 的 Cons 原文："You might make the code more complicated by applying the pattern to a highly cohesive class."（把高内聚的类硬拆两半只会更难懂。）
- 接线由调用方完成（构造时注入实现），接错组合编译器不报错，只在运行期表现为行为不符，需要靠测试兜住。
- 误用信号：目前只有一种实现、也看不到第二种实现要出现，却已拆出两层抽象（投机性一般化）；或两条层次的方法几乎一一对应、只是换了名字，说明两个维度并不正交，应合并回一个类。

**易混辨析**：与策略模式的区别在意图——两者结构相同（上下文持有可变实现并委托），桥接是为了让两条层次各自成体系、各自扩展（abstraction/platform、interface/implementation），通常在构造时就把实现固定；策略是为了在同一上下文里切换一段算法。SourceMaking 也指出 State、Strategy、Bridge 共享 "handle/body" 结构，差别仅在意图。与适配器的区别：适配器是事后让两个已存在的不兼容接口协作，桥接是在设计期就为两条维度预留分离。

---

## 3. 组合模式 (Composite)

**意图**：把对象组合成树结构来表示整体-部分层次，使客户端一致地对待单个对象与对象组合。SourceMaking 原文为 "Compose objects into tree structures to represent whole-part hierarchies"，核心是递归组合（容器中装的是组件，而组件本身可能又是容器）；Wikipedia 表述为客户端把单个实例与同一类型的组合当作同一类型处理。

**适用条件**（可观察的前置条件）：
- 领域本身是整体-部分层次：目录含条目、条目可能是目录；菜单含菜单项、菜单项可能是菜单；表达式含操作数、操作数可能是表达式。
- 客户端目前不得不在处理前判断"这是叶子还是容器"（`if (node is Folder)`），这类分支是引入该模式的可观察信号。
- 对单个对象与对整棵树的同一操作应产生同构结果（"求大小"对文件与目录都有意义），且调用沿树逐层下传、树的构造在运行期可能变化。

**不要用于**：结构固定且只有两层时（手工递归加类型判断更直接）；叶子和容器本来就不该共享同一个接口时（统一对待本身没有语义）。

**角色**：Component（叶子与容器共用的抽象，声明需要被统一对待的操作）；Leaf（叶子，直接实现 Component，无子节点）；Composite（容器，持有 `System.Collections.Generic.IReadOnlyList<T>` 之类的子节点集合，实现子节点管理并把统一操作递归委托给子节点，T 即 Component 角色）；Client（只依赖 Component）。

**C# 最小实现**：

```csharp
namespace DesignPatterns.Samples.Structural;

// Component：叶子与容器共用的同一个接口
public interface IWorkspaceNode
{
    System.String Name { get; }
    System.Int64 SizeInBytes();
}

// Leaf：没有子节点
public sealed class WorkspaceFile(System.String name, System.Int64 size) : IWorkspaceNode
{
    public System.String Name { get; } = name;
    public System.Int64 SizeInBytes() => size;
}

// Composite：持有子节点集合并递归委托；Add 留在容器上，换取类型安全
public sealed class WorkspaceFolder(System.String name) : IWorkspaceNode
{
    private readonly System.Collections.Generic.List<IWorkspaceNode> _children = [];
    public System.String Name { get; } = name;
    public void Add(IWorkspaceNode child) => _children.Add(child);
    public System.Int64 SizeInBytes()
    {
        System.Int64 total = 0;
        foreach (IWorkspaceNode child in _children) { total += child.SizeInBytes(); }
        return total;
    }
}
```

**代价与误用信号**：
- 核心取舍是"透明 vs 类型安全"。SourceMaking 用一整节讨论：要让客户端统一对待叶子与容器，`Add`/`Remove` 就必须上提到 Component 接口，代价是客户端可对叶子执行无意义的增删；留在 Composite 类里能保住类型安全，却失去透明性。Wikipedia 记录 GoF 的写法偏重透明性并讨论两种取舍，并指出若树在构造后不再变化，类型安全变体更合适。
- 误用信号：叶子类里出现抛 `System.NotSupportedException` 的 `Add`/`Remove`，说明选了透明性取向却并不需要统一增删；或客户端布满向下转型（`if (node is WorkspaceFolder folder)`）后再调子节点管理方法，说明透明性这一主要收益并未拿到。
- 误用信号：递归遍历没有深度上限保护，极深或成环的结构会栈溢出；子节点集合被外部直接改写会破坏树的不变量。

**易混辨析**：与装饰器的区别在于结构图相似（都靠递归组合组织数量不定的对象），SourceMaking 的判据是意图：Composite 关注"表示"（整体-部分），Decorator 关注"修饰"（给单个对象叠加职责），装饰器可看作"只有一个组件的退化组合"，反之装饰器不用于对象聚合。迭代协议不属于该模式本身（SourceMaking 明确说提供迭代协议在组合模式之外）；享元则常用于实现可共享的叶节点。

---

## 4. 装饰器模式 (Decorator)

**意图**：动态地给对象附加额外职责，为扩展功能提供比继承更灵活的替代方案。SourceMaking 原文为 "Attach additional responsibilities to an object dynamically"；Wikipedia 补充它支持单一职责原则与开闭原则——功能可分散到各司其职的类中，且无需修改源码即可扩展。

**适用条件**（可观察的前置条件）：
- 存在"一个核心对象 + 若干可选修饰"的形态，修饰种类与叠加次数在设计期无法穷举（否则子类组合就够用）。
- 需要在运行期按对象（而不是按类）增删职责，同一类的不同实例承担不同职责。
- 客户端可以只依赖一个稳定的共同接口、不需要知道包装了几层，且修饰之间彼此独立可任意次序叠放（若次序有强约束，需要另行表达）。

**不要用于**：职责组合在编译期就固定、永远只有一种叠法时（直接写在方法里更清楚）；需要改变被包装对象的接口而不是叠加职责时（那是适配器）。

**角色**：Component（共同接口，保证被装饰者与装饰者可互相替换）；Concrete Component（核心对象）；Base Decorator（实现 Component 并持有另一个 Component，默认把调用转交出去）；Concrete Decorator（在转发前后加入自己的行为）；Client（自行决定包装的类型与次序）。推荐"接口 + 组合"：装饰器实现接口并持有一个同接口成员，而不是继承具体组件类。

**C# 最小实现**：

```csharp
namespace DesignPatterns.Samples.Structural;

// Component：客户端只需认识这个接口
public interface IRowWriter
{
    void WriteRow(System.String row);
}

// Concrete Component：核心职责
public sealed class CsvRowWriter : IRowWriter
{
    public void WriteRow(System.String row) => System.Console.WriteLine(row);
}

// Base Decorator：实现接口 + 组合，不继承具体组件类
public abstract class RowWriterDecorator(IRowWriter inner) : IRowWriter
{
    public virtual void WriteRow(System.String row) => inner.WriteRow(row);
}

// Concrete Decorator：转发前后附加行为，可按任意次序再叠一层
public sealed class UpperCaseRowWriter(IRowWriter inner) : RowWriterDecorator(inner)
{
    public override void WriteRow(System.String row) => base.WriteRow(row.ToUpperInvariant());
}
```

**代价与误用信号**：
- 被装饰对象的核心身份被藏进装饰器内部：SourceMaking 明确指出"核心对象的身份现在被隐藏在装饰器对象里，想直接访问核心对象就成了一个麻烦"；叠层后调试栈与异常栈上会出现一串同接口类型，可读性下降。
- 误用信号：装饰器改变了接口语义（返回类型不同、对某些输入额外抛异常），客户端无法再按原接口无条件替换被装饰对象；或叠放次序本是硬约束（如必须先压缩再加密），却没用类型或工厂把约束表达出来，只能靠调用方记住顺序。
- 误用信号：组合在编译期就固定、永远只有一种叠法，却引入运行期装饰链——多出的间接层没有换到任何独立变化。Wikipedia 另记录：需要对一批对象批量施加不同装饰组合时，与集合的交互会变复杂，往往要借助适配器或访问者统一接口。

**易混辨析**：与适配器的区别在于适配器换掉接口，装饰器保持或增强接口，因而只有装饰器支持递归组合；与代理的区别在于两者结构和实现方式相似（都持有被转发对象的引用），SourceMaking 说它们"目的不同、结构相同"：代理控制访问，装饰器叠加职责；与组合模式的区别在于装饰器可视为"只有一个组件的退化组合"，但它加的是职责而非聚合；与策略模式的区别借用 SourceMaking 的比喻：装饰器换对象的外表，策略换对象的内部算法。

---

## 5. 外观模式 (Facade)

**意图**：为子系统中的一组接口提供一个统一的高层接口，使子系统更容易使用。SourceMaking 原文为 "Provide a unified interface to a set of interfaces in a subsystem"，并强调它只是"用一个更简单的接口把复杂子系统包起来"；Wikipedia 补充它可提高库的可读性与可用性，并可充当把紧耦合系统重构成松耦合的起点。

**适用条件**（可观察的前置条件）：
- 完成一个常见任务需要按固定次序调用子系统的多个对象，调用方被迫了解子系统内部结构。
- 同一段"编排代码"已经在第二处、第三处调用方重复出现（SourceMaking 的检查清单也把"是否有额外外观能带来价值"列为一步）。
- 子系统复杂度高或源码不可得，调用方需要一个稳定的少量方法入口，且需求只是"简化入口"而非"新增功能"。

**不要用于**：调用方本来就只需要一步就能完成（用扩展方法或普通方法即可）时；子系统的所有能力都必须原样暴露给高级用户时（外观会成为限制，并被迫开逃生舱口）。

**角色**：Facade（持有或创建子系统对象，把一次调用编排成对若干子系统的调用）；Additional Facade（外观膨胀后拆出的第二个入口，避免单个外观负载过多）；Complex Subsystem（被简化的若干类）；Client（只依赖外观，不再直接与子系统交互）。SourceMaking 提醒外观应保持"简单的主张者/促成者"角色。

**C# 最小实现**：

```csharp
namespace DesignPatterns.Samples.Structural;

public sealed class ImportRequestValidator
{
    public System.Boolean TryValidate(System.String path, out System.String reason)
    {
        reason = System.String.Empty;
        return !System.String.IsNullOrWhiteSpace(path);
    }
}

public sealed class RawRowReader
{
    public System.Collections.Generic.IReadOnlyList<System.String> Read(System.String path)
        => System.IO.File.ReadAllLines(path);
}

public sealed class ImportAuditLog
{
    public void Record(System.String message) => System.Console.WriteLine(message);
}

// Facade：只做编排与转发，不新增业务规则
public sealed class ImportFacade
{
    private readonly ImportRequestValidator _validator = new();
    private readonly RawRowReader _reader = new();
    private readonly ImportAuditLog _log = new();

    public System.Int32 Import(System.String path)
    {
        if (!_validator.TryValidate(path, out System.String reason))
        {
            throw new System.ArgumentException(reason, nameof(path));
        }

        System.Collections.Generic.IReadOnlyList<System.String> rows = _reader.Read(path);
        _log.Record($"imported {rows.Count} rows from {path}");
        return rows.Count;
    }
}
```

**代价与误用信号**：
- SourceMaking 指出：若外观成为访问子系统的唯一入口，它会限制"高级用户"所需的功能与灵活性；同一节还明确警告外观不应变成全知的 oracle 或"上帝对象"。
- 外观本身是新一层依赖：它在内部直接 `new` 子系统对象时，单元测试无法替换子系统实现（上例正是这种形态）；需要可测性时应改为构造函数注入。
- 误用信号：外观里累积了子系统自身的业务规则、状态与分支判断；或所有调用方都只能走外观，团队不断在外观上开"逃生舱口"（暴露内部对象或内部类型），说明简化接口已不够用，应拆分或重画边界。

**易混辨析**：与中介者的区别——SourceMaking 认为两者相似但有三点不同：中介者集中并"增加价值"（承载同事对象之间原本分散的通信逻辑），且同事对象知道并引用中介者；外观只是给子系统一个更简单的接口、不新增功能，子系统类也不知道外观存在。与适配器的区别——SourceMaking 明确说判据不是"包裹几个类"（外观可以只包一个复杂类，适配器也可以适配多个类），而是意图。与享元的区别——享元讲如何造很多小对象，外观讲如何用一个对象代表整个子系统。

---

## 6. 享元模式 (Flyweight)

**意图**：运用共享技术有效地支持大量细粒度对象。SourceMaking 原文为 "Use sharing to support large numbers of fine-grained objects efficiently"；Wikipedia 表述为"通过与其他相似对象共享部分数据来最小化内存占用"，并指出该概念由 Paul Calder 与 Mark Linton 于 1990 年为 WYSIWYG 文档编辑器高效处理字形信息而提出。

**适用条件**（可观察的前置条件）：
- 对象数量极大且大量对象在大部分数据上重复，内存占用已成为可测量的瓶颈（SourceMaking 检查清单第一条就要求确认"对象开销确实构成需要处理的问题"）。
- 状态可切分为"与上下文无关、可共享"的内在状态和"依赖上下文、不可共享"的外在状态。
- 调用方有能力也有意愿承接职责再分配：外在状态由客户端计算或查表并在每次调用时作为参数传入，且共享对象构造后不再变化。

**不要用于**：被共享的那部分状态本身可变时（共享即竞态）；对象数量不大、内存根本不是瓶颈时；无法把内在状态与外在状态干净切分时。

**角色**：Flyweight（持有内在状态，操作接收外在状态作为参数）；Flyweight Factory（缓存并复用享元实例，客户端必须通过工厂而不是 `new` 获取对象）；Context/Client（保存或计算外在状态并在调用时传入）。SourceMaking 强调享元不能独立存在：凡使共享不可能的属性，都必须由客户端在请求时提供。

**C# 最小实现**：

```csharp
namespace DesignPatterns.Samples.Structural;

// Flyweight：内在状态，构造后不可变，因而可被无限制共享
public sealed class GlyphMetric(System.Char symbol, System.Double width)
{
    public System.Char Symbol { get; } = symbol;
    public System.Double Width { get; } = width;
}

// Flyweight Factory：同一个符号只创建一次；缓存会被多线程共享，必须用并发字典
public sealed class GlyphMetricFactory
{
    private readonly System.Collections.Concurrent.ConcurrentDictionary<System.Char, GlyphMetric> _cache = new();

    // GetOrAdd 的工厂委托可能被并发执行、构造出多个实例，但只有一个会被缓存并返回；
    // 享元不可变，多余的实例随即被丢弃，因此不需要在访问处再加锁
    public GlyphMetric Get(System.Char symbol)
        => _cache.GetOrAdd(symbol, static key => new GlyphMetric(key, 0.6));
}

// 外在状态由调用方提供，不放进享元
public static class TextMeasurer
{
    public static System.Double Measure(
        System.Collections.Generic.IReadOnlyList<System.Char> text,
        GlyphMetricFactory factory)
    {
        System.Double total = 0;
        foreach (System.Char symbol in text) { total += factory.Get(symbol).Width; }
        return total;
    }
}
```

**代价与误用信号**：
- 职责从对象转移到客户端：外在状态必须由调用方查找或计算并在每次调用时传入，接口因此变宽、调用点变啰嗦。SourceMaking 把它写进检查清单第一条（客户端"有能力且愿意"接受这一再分配）。
- 共享的是同一个实例，任何一处写入对所有使用者可见。Wikipedia 的实现细节一节指出：不可变对象易于共享但每次状态变化都要新建，可变对象便于缓存复用但"状态高度可变时共享通常不可行"，并提醒多线程下要么预先批量创建、要么保证实例化单线程。
- 误用信号：把随使用场景变化的数据留在享元里（当前坐标、当前用户、当前批次）——这就是共享可变状态；对象数量本不大、内存也不是瓶颈却硬拆内外状态并加一层缓存查找，只买到额外开销；或忽略工厂缓存自身的线程安全与增长上限。

**易混辨析**：与对象池的区别——对象池复用"同一时刻只借给一个使用者的实例"（借出期间独占，归还后重置），享元共享的是"同一时刻可被任意多个使用者同时读取的同一份状态"（共享对象不应被写入）。与外观的区别（SourceMaking 原话）：享元讲如何造出很多小对象，外观讲如何用一个对象代表整个子系统。与状态、解释器的关系：SourceMaking 指出享元解释了状态对象何时可以共享，解释器抽象语法树中的终结符也可以被共享；享元常与组合模式配合实现可共享的叶节点。

---

## 7. 私有类数据模式 (Private Class Data)

**意图**：把类属性与其操作封装起来。SourceMaking 把意图列为四条：控制对类属性的写访问、把数据与使用数据的方法分离、封装类数据初始化，以及 "Providing new type of `final` - final after constructor"（提供一种"构造之后再不可写"的 final）。iluwatar/java-design-patterns 的条目表述为"限制对对象内部状态的访问，通过受控的方法访问提升安全性、降低数据被破坏的风险"。

**适用条件**（可观察的前置条件）：
- 类中存在"只应在构造期赋值、之后任何方法（包括类自己的方法）都不应改动"的字段，而目标语言无法用一次性的只读声明直接表达。
- 一组字段总是一起出现、一起传递，需要作为不可写单元在多个方法之间流转。
- 需要把"数据表示"的变更与"使用数据的方法"的变更分开：操作数据的方法不建立在数据类上，而是由外层类型接收该数据对象来完成。
- 类自身的方法存在误写字段的风险（例如在 `Taste()` 里顺手递减食材数量），需要从结构上消除这种可能。

**不要用于**：`private readonly` / `{ get; }` / `{ get; init; }` / `record` 已经能表达"构造后不可写"时（此时它只是样板）；并不需要把数据与操作它的方法物理分离、只是想让几个字段一起传递时。

**角色**：Data Class（只承载数据，通过构造函数或对象初始化器一次性初始化，对外只暴露读取通道，自身不含业务方法）；Main Class/外层服务（持有或接收 Data Class 实例，操作数据的业务方法只能读、不能写）；Getter/Setter（SourceMaking 检查清单要求：每个属性通过 getter 暴露，只有确实需要在后续变更的属性才通过 setter 暴露）。

**C# 最小实现**：

```csharp
namespace DesignPatterns.Samples.Structural;

// Data Class：只暴露 init 只读属性，构造后不存在任何写入通道，自身不含业务方法
public sealed class StewData
{
    public System.Int32 Potatoes { get; init; }
    public System.Int32 Carrots { get; init; }
}

// Main Class/外层服务：数据与使用数据的方法物理分离——方法留在这里，由它接收数据对象
public sealed class StewReporter
{
    public System.String Describe(StewData data)
        => $"stew: {data.Potatoes} potatoes, {data.Carrots} carrots";

    public System.Int32 TotalIngredients(StewData data)
        => data.Potatoes + data.Carrots;
}
```

**代价与误用信号**：
- 该模式在权威目录中被列为补充模式，原因是它的核心目标之一在现代语言里已被语言特性取代。SourceMaking 自己把意图之一定义为"构造之后不可写"，而这正是 C# `private readonly` 字段、`{ get; }` / `{ get; init; }` 属性与 `record` 类型的语义，且由编译器在编译期强制，比"把字段搬进另一个类再只暴露 getter"更直接、样板更少；因此现代 C# 中 `record` / `readonly` 已覆盖"构造后不可写"这一条，只有确实需要把数据表示与操作它的方法物理分离（数据类只承载状态，使用方法的外层类型可独立演化）时，才值得单独建模。
- iluwatar 条目把权衡写成两条：额外的 getter/setter 调用带来轻微性能开销；为数据访问多出的一层方法会增加类设计的复杂度。
- 误用信号：数据类上仍保留公共 setter 或 `{ get; set; }`（写权限没有被收窄，模式的收益全部落空）；只有两三个原本就能写成 `readonly` 的字段却引入数据类；或主类把数据类实例直接暴露给外部（公共属性返回同一个实例），外部仍可绕过主类改写数据。

**易混辨析**：与代理的区别——iluwatar 的对照写得很清楚：两者都限制访问，但代理控制的是"对对象本身的访问"，私有类数据控制的是"对数据的访问"。与 C# 语言特性的关系——`readonly` / `init` / `record` / 不可变属性解决的是同一问题（构造后不可写）并且由编译期强制，因此先考虑语言特性、再考虑该模式是正确顺序。与单纯用于传输的数据载体（DTO）的区别——该模式关心的是"禁止写入、把数据与使用它的方法分离"，为传输而存在的类型不承担这个约束。

---

## 8. 代理模式 (Proxy)

**意图**：为其他对象提供一种代理以控制对这个对象的访问。SourceMaking 的完整表述是"提供一个替身或占位符来控制对另一个对象的访问"，并补充"用额外一层间接来支持分布式、受控或智能的访问"；Wikipedia 表述为"代理是一个包装者或代理对象，客户端调用它来访问幕后的真实对象"。

**适用条件**（可观察的前置条件）：
- 需要对访问本身施加控制：延迟创建、权限判定、远程转发、缓存或引用计数。
- 真实对象创建代价高（或此时根本不该创建），只有在第一次真正被请求时才应实例化。
- 代理与真实对象可以共享同一个接口，客户端在不改代码的前提下改用代理，且控制逻辑属于"访问"层面而不是"新增职责"。

**不要用于**：目的其实是叠加职责时（那是装饰器）；只是想延迟初始化一次时（`System.Lazy<T>` 已覆盖，不必手写完整代理类）。

**角色**：Subject/Service Interface（代理与真实对象共同的接口，使两者可互换）；RealSubject/Service（真正的实现，可能昂贵、远程或敏感）；Proxy（实现 Subject，持有真实对象引用，在转发前后施加控制逻辑）；Client（只依赖 Subject）。SourceMaking 列出四类常见代理：虚拟代理（为"创建昂贵"的对象占位，首次请求时才创建）、远程代理（为不同地址空间中的对象提供本地代表，即 RPC/CORBA 里的 stub）、保护代理（转发前检查调用者权限）、智能代理（访问时插入额外动作，如引用计数、首次引用时把持久对象载入内存、访问前检查对象是否被锁定）。

**C# 最小实现**：

```csharp
namespace DesignPatterns.Samples.Structural;

public interface IInvoiceArchive
{
    System.String Load(System.String id);
}

public sealed class RemoteInvoiceArchive : IInvoiceArchive
{
    public System.String Load(System.String id) => System.String.Concat("invoice:", id);
}

// 虚拟代理（透明代理）：接口不变，首次访问时才构造真实对象
public sealed class LazyInvoiceArchive : IInvoiceArchive
{
    private readonly System.Lazy<IInvoiceArchive> _real =
        new System.Lazy<IInvoiceArchive>(() => new RemoteInvoiceArchive());

    public System.String Load(System.String id) => _real.Value.Load(id);
}

public interface ICurrentUser
{
    System.Boolean CanReadInvoices { get; }
}

// 保护代理：接口同样不变，但转发前先判定调用者权限
public sealed class GuardedInvoiceArchive(IInvoiceArchive inner, ICurrentUser user) : IInvoiceArchive
{
    public System.String Load(System.String id)
        => user.CanReadInvoices ? inner.Load(id) : throw new System.UnauthorizedAccessException($"denied: {id}");
}
```

**代价与误用信号**：
- 每次调用都多一次转发；Wikipedia 指出代理可以只是转发、也可以附加逻辑（如对资源密集型操作做缓存、在操作前检查前置条件），附加逻辑越多，开销与行为差异越大。虚拟代理还会把初始化失败推迟到第一次使用时才暴露。
- 代理与真实对象必须严格同接口：真实对象接口变化时代理需同步变化，否则会退化为语义漂移（编译不报错但行为不一致）。
- 误用信号：代理里偷偷塞业务逻辑（保护代理顺手补数据、虚拟代理顺手改默认值），使同一接口出现两个功能不同的实现；用代理抹平远程调用的网络失败与超时，让调用方以为它是本地对象；或只需一次性的延迟初始化却手写了完整代理类（`System.Lazy<T>` 已覆盖该场景）。
- 误用信号：把"运行时动态代理"（`System.Reflection.DispatchProxy`）当成万能横切手段——它带来的可调试性、性能与裁剪/AOT 约束应先在目标框架上实测，不能凭机制名推断能力。

**易混辨析**：透明代理与保护代理的区分——透明代理（虚拟、远程、智能引用）不改变调用结果，只改变"何时、在哪里"执行，客户端不应察觉差异；保护代理在转发前做权限判定、会拒绝调用，因而对客户端可见（例如抛出 `System.UnauthorizedAccessException`），其行为差异必须写进接口契约。与其他包装模式的区分（SourceMaking 的规则）：适配器提供不同的接口，代理提供相同的接口，装饰器提供增强的接口；代理与装饰器"目的不同、结构相同"，都持有被转发对象的引用，区别在于是控制访问还是叠加职责。关于动态代理：运行时基类库另有一条按接口生成代理类型的路径 `System.Reflection.DispatchProxy`（已在本机 .NET 10 参考程序集 `Microsoft.NETCore.App.Ref/10.0.2` 中核实该类型存在；其文档摘要为 "Provides a mechanism for instantiating proxy objects and handling their method dispatch"，公开成员含 `Create(System.Type, System.Type)`、`Create<T, TProxy>()` 与 `Invoke(System.Reflection.MethodInfo, System.Object[])`）。它适用于需要按接口批量生成转发实现的场合；是否选用以及它与手写代理的取舍，应以目标框架文档与实测为准，本文件不对其运行行为下进一步结论。

---

## 易混模式对照

| 模式 A | 模式 B | 判别问题（一句话分开两者） |
| --- | --- | --- |
| 适配器 (Adapter) | 装饰器 (Decorator) / 代理 (Proxy) | 目标接口与原有接口的关系是什么：换成调用方期望的另一套接口是适配器；接口不变、只是增强职责是装饰器；接口不变、只是控制对同一对象的访问是代理。 |
| 桥接 (Bridge) | 策略 (Strategy) | 拆出的两层是否要各自长成体系并独立扩展：要（抽象与实现各自成族，通常在构造时绑定）是桥接；只是为在同一上下文里替换一段算法是策略。 |
| 组合 (Composite) | 装饰器 (Decorator) | 递归组合是为了"表示整体-部分"还是"给单个对象层层加职责"：表达包含关系是组合；只有一个被包装对象、目的是叠加职责是装饰器。 |
| 外观 (Facade) | 中介者 (Mediator) | 子系统是否知道并依赖这个中间人：外观单向、子系统不认识它、也不新增功能；中介者双向、同事对象认识它、并集中了原本分散的协作逻辑。 |
| 享元 (Flyweight) | 对象池 (Object Pool) | 被共享的实例是"同时可被多方读取的同一份状态"还是"同一时刻只借给一个使用者的对象"：前者是享元（共享对象不应被写入），后者是对象池（借出期间独占、归还后重置）。 |
| 代理 (Proxy) | 装饰器 (Decorator) | 这层包装是为了控制访问（延迟创建、权限、缓存、远程）还是为了叠加职责：控制访问是代理；可任意递归叠加职责是装饰器。 |
| 适配器 (Adapter) | 桥接 (Bridge) | 是事后补救还是事前设计：两个已存在的类互不兼容、想把它们接起来是适配器；两个维度需要各自演化、在设计期就预留分离是桥接。 |
| 适配器 (Adapter) | 外观 (Facade) | 是让既有接口变得可用（复用旧接口、通常对应一个被适配方）还是为子系统定义一个更简单的新接口（不新增功能、通常跨多个子系统类）：前者是适配器，后者是外观。 |
| 私有类数据 (Private Class Data) | 代理 (Proxy) | 被控制的是"数据"还是"对象"：收窄字段写权限、把数据与使用它的方法分开是私有类数据；控制对整个对象的访问是代理。 |

## 常见误解与反模式

（各模式自身的误用信号见对应条目的「代价与误用信号」；本节只列跨模式的共性红线。）

- 多个包装模式互相叠加后，调试栈与异常栈上会出现一长串实现同一接口的类型，靠读栈无法还原对象图：应提供受控的解包手段或在日志中打印包装链，而不是让"包装了几层"成为只能靠猜的隐含状态。
- 把模式当装饰性命名：用 `Adapter`/`Builder`/`Manager` 之类的模式名给类型命名，或用注释标注"这里是某某模式"，会让调用方按模式名而不是领域职责理解代码；类型应用领域名，模式只是实现细节（R20）。
- 投机性泛化与抽象通货膨胀：只有一种实现、看不到第二种实现要出现，却预先拆出桥接式、策略式或其他"为以后预留"的扩展点；或为一个功能一次引入 5 个以上新类型。扩展点只在第二个实现出现时加，新增类型数应与问题规模相称（R3）。
- 同一层包装同时承担多种模式的职责：既转换接口、又控制访问、又叠加职责，会使这层无法归类、无法单独测试，出问题时也说不清该改哪一侧；每层包装只做一件事。
