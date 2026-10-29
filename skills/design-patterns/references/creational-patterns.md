# 创建型模式 (Creational Patterns)

> 本文代码示例的命名空间（`Acme.*`）为示意，不对应 RxToolkits 仓库中的实际类型；示例只演示模式结构，不代表仓库已有同名类型。

## 概览

创建型模式共同解决的问题是：把「实例化」从使用方剥离出去。使用方本不该知道具体类的名字、构造参数如何拼装、哪个实例已经被创建过；它只应声明「我需要一个满足某契约的对象」。创建型模式把这段知识收拢到一处，从而让使用方依赖抽象而不是具体类型，并让创建策略（复用、克隆、分步装配、限制实例数）可以独立于业务逻辑变化。

| # | 模式 | 一句话意图 | 最关键的代价/风险 |
| --- | --- | --- | --- |
| 1 | 单例模式 (Singleton) | 保证一个类只有一个实例，并提供全局访问点 | 等价于一个被美化的全局变量：隐藏真实依赖、让调用方无法替换、并行测试时共享可变状态 |
| 2 | 工厂方法模式 (Factory Method) | 定义创建接口，由子类决定实例化哪个具体类 | 每新增一个产品类型就要新增一个创建者子类，继承层次随产品数量膨胀 |
| 3 | 抽象工厂模式 (Abstract Factory) | 在一个接口中集中生产一族相互配套的产品，而不指定其具体类 | 新增「一个产品种类」必须改动抽象工厂接口及其全部实现，扩展方向是单向的 |
| 4 | 建造者模式 (Builder) | 把复杂对象的构造拆成分步过程，同一过程可产出不同表示 | 为一次构造引入额外的可变的构建器类型；必填约束无法在编译期表达，只能在 `Build()` 里运行期校验 |
| 5 | 原型模式 (Prototype) | 通过复制已有实例创建新对象，而不依赖具体类 | 浅拷贝与深拷贝的混淆：克隆体与原对象共享引用类型字段，改一个会连带改另一个 |
| 6 | 对象池模式 (Object Pool) | 复用已初始化的实例，避免反复创建与销毁 | 必须与调用方约定归还契约；漏归还、状态未重置、异常路径不归还都会造成资源泄漏或脏状态 |

## 1. 单例模式 (Singleton)

**意图**：保证一个类只有一个实例，并提供一个全局访问点。SourceMaking 的表述是「确保一个类只有一个实例，并为其提供全局访问点」，并强调它同时承担了「延迟初始化 / 首次使用时初始化」这一职责。

**适用条件**（可观察的前置条件）：
- 该实例的所有权无法合理地指派给某个既有对象，也就是没有天然的宿主可以持有它并把它传递下去。
- 延迟初始化有价值：实例的构造有可测量的成本，而程序可能整个生命周期都不需要它。
- 全局访问点本来不存在，且引入它不会让调用方绕开依赖注入的传递路径。
- 存在真实的、外在的独占约束（独占设备、单写者文件、进程内唯一缓存），而不只是「创建一个太麻烦」。

**不要用于**：该实例有自然宿主、能由某个既有对象持有并顺着构造参数传递下去时；引入它的动机只是少写几个构造参数时；实例上需要存放会被多处改写的可变状态时（这是「单例即全局可变状态」反模式的入口）。

**角色**：Singleton 自身同时是三个角色——唯一的实例、持有该实例的私有静态字段、以及公开的静态访问器（`Instance`）。构造函数私有化，强制所有调用方只能经由访问器获得对象。

**C# 最小实现**：

```csharp
using System;

namespace Acme.Runtime;

public sealed class TelemetryBuffer : System.IDisposable
{
    // 静态字段初始化器由运行时在类型初始化期间执行，并受类型初始化锁保护，
    // 因此即使在多线程首次访问下也只会构造一个实例（CLI 类型初始化语义）。
    private static readonly TelemetryBuffer Shared = new TelemetryBuffer();

    // 唯一允许被替换为 null 的位置在 Dispose 中，故需显式标注可空；
    // 初值取 Shared，否则 Instance 永远只会抛 ObjectDisposedException。
    private static TelemetryBuffer? _current = Shared;

    public static TelemetryBuffer Instance => _current ?? throw new System.ObjectDisposedException(nameof(TelemetryBuffer));

    private TelemetryBuffer()
    {
    }

    public void Write(System.String message)
    {
        System.ArgumentNullException.ThrowIfNull(message);
        // 业务逻辑。
    }

    public void Dispose()
    {
        _current = null;
    }
}
```

需要真正延迟到首次使用时才构造时，用 `System.Lazy<T>`；它的默认线程安全模式是 `System.Threading.LazyThreadSafetyMode.ExecutionAndPublication`，即加锁保证只有一个线程完成初始化，且初始化函数的异常会被缓存并在此后每次访问时重抛。不要选择 `PublicationOnly` 来「省锁」，那会允许并发线程各构造一份再丢弃，对非幂等的初始化是错的。

**代价与误用信号**：它同时解决了「唯一实例」和「全局访问」两个问题，因此天生违反单一职责。误用信号：调用方把依赖直接从单例里取出而不是由构造参数注入；单元测试为了隔离而需要重置静态状态；单例上出现可变的全局状态；为每个测试夹具并行运行时相互污染。SourceMaking 对此的评述很直接：单例对全局数据而言只是换了个名字，问题本身没有被解决。

**易混辨析**：与静态类的区别在于，单例是**对象**：可以实现接口、可以被当作参数传入、可以让实现类持有实例状态，而静态类无法参与多态与替换。与「依赖注入容器里的单例生命周期」的区别在于，后者把唯一性交给容器管理，调用方仍然通过构造参数声明依赖——绝大多数情况下这才是更可测试的形态。与享元模式的区别在于，享元可以有多份实例、且实例应当不可变，单例只有一个实例且可以是可变的。

## 2. 工厂方法模式 (Factory Method)

**意图**：定义一个用于创建对象的接口，但让子类决定实例化哪一个类；工厂方法使一个类的实例化延迟到其子类。Refactoring.Guru 把它概括为「在父类中提供创建对象的接口，但允许子类改变将被创建的对象的类型」，别名「虚拟构造器」。

**适用条件**（可观察的前置条件）：
- 代码在编写时无法预知将要处理的对象的确切类型与依赖，需要由配置或环境在运行时决定。
- 存在一个稳定的框架骨架，需要把「创建哪一部分」这一可变点留给使用方覆盖——工厂方法本质上是模板方法在创建维度上的特化。
- 同一个创建点已经出现多处 `if`/`switch` 分派到不同构造调用，且每新增一种类型都要改动这些分派点。
- 希望创建的返回值参与多态：返回声明类型是抽象产品，实际可以是子类，也可以复用已有实例而不是新建。

**不要用于**：产品只有一种实现、在代码里看不到第二种实现或配置分支时（直接 `new` 即可）；调用点在编写时就知道要实例化哪个具体类型、引入抽象只会让读者多跳一层时。

**角色**：Product（产品接口，声明所有产品共有的操作）、ConcreteProduct（具体产品）、Creator（创建者，声明工厂方法并通常已包含依赖产品的核心业务逻辑）、ConcreteCreator（覆盖工厂方法以改变产出类型）、Client（只依赖 Creator 与 Product 的抽象）。注意工厂方法并不是 Creator 的主要职责。

**C# 最小实现**：

```csharp
using System;

namespace Acme.Export;

public interface IRowFormatter
{
    System.String Format(System.String raw);
}

public sealed class PlainTextFormatter : IRowFormatter
{
    public System.String Format(System.String raw) => raw;
}

public sealed class CsvFormatter : IRowFormatter
{
    public System.String Format(System.String raw) => "\"" + raw.Replace("\"", "\"\"") + "\"";
}

public abstract class RowWriter
{
    // 依赖方向：Writer 依赖抽象产品，而不是某个具体格式化器。
    protected abstract IRowFormatter CreateFormatter();

    public System.String Write(System.Collections.Generic.IReadOnlyList<System.String> cells)
    {
        IRowFormatter formatter = this.CreateFormatter();
        System.Collections.Generic.List<System.String> parts = new System.Collections.Generic.List<System.String>();
        foreach (System.String cell in cells)
        {
            parts.Add(formatter.Format(cell));
        }

        return System.String.Join(",", parts);
    }
}

public sealed class CsvRowWriter : RowWriter
{
    protected override IRowFormatter CreateFormatter() => new CsvFormatter();
}
```

**代价与误用信号**：代价是引入一条平行的创建者继承层次——产品每增加一种，创建者也要增加一个子类；当产品族有两个以上变化维度时，子类数量会相乘。误用信号：工厂方法里出现按参数分支的 `switch`（说明变化点放错了位置，应改为子类或注册表）；只有一个具体创建者且短期没有第二个；创建的返回值被调用方立即向下强制转换回具体类型（抽象形同虚设）。

**易混辨析**：与抽象工厂的区别是「一个产品」与「一族产品」：工厂方法的产出是单个产品，扩展靠继承；抽象工厂的产出是一组相互配套的产品，扩展靠替换整个工厂对象。与简单工厂（一个静态方法内做 `switch`）的区别是，简单工厂把变化集中但没有消除对具体类型的依赖，也谈不上让子类决定。与原型模式的区别在于创建机制：SourceMaking 的概括是「工厂方法：通过继承创建；原型：通过委托创建」。

## 3. 抽象工厂模式 (Abstract Factory)

**意图**：提供一个接口，用于创建一系列相关或相互依赖的对象家族，而无需指定它们的具体类。Refactoring.Guru 的表述是「让你生产一族相关对象，而不必指定它们的具体类」，其核心保证是同一工厂产出的产品彼此配套。

**适用条件**（可观察的前置条件）：
- 产品按「变体」成组出现，且同一变体内的产品必须配套使用，混用会产生不一致（跨平台控件、同一格式族的读写器、同一协议的编解码器）。
- 系统需要在运行时整体切换到另一个产品族，而客户端代码不应随之改动。
- 类中已经堆叠了多个工厂方法，且这些方法彼此相关、模糊了该类的主要职责，值得整体外提为一个工厂对象。
- 扩展方向以「新增变体」为主，而不是以「新增产品种类」为主。

**不要用于**：产品只有一个变化维度时（抽象工厂只会多出一层接口，用工厂方法即可）；产品族集合已经稳定、可以断言不会再新增变体时。

**角色**：AbstractProduct（每个产品种类一个接口）、ConcreteProduct（按变体分组实现）、AbstractFactory（为每个产品种类声明一个创建方法，返回抽象产品）、ConcreteFactory（对应一个变体，只创建该变体的产品）、Client（只通过抽象接口使用工厂与产品，通常在启动阶段选定一个具体工厂）。

**C# 最小实现**：

```csharp
using System;

namespace Acme.Ui;

public interface IButton
{
    System.String Render();
}

public interface ICheckBox
{
    System.String Render();
}

public sealed class LightButton : IButton
{
    public System.String Render() => "[ Light Button ]";
}

public sealed class LightCheckBox : ICheckBox
{
    public System.String Render() => "[ ] Light CheckBox";
}

public interface IUiFactory
{
    IButton CreateButton();

    ICheckBox CreateCheckBox();
}

public sealed class LightThemeFactory : IUiFactory
{
    public IButton CreateButton() => new LightButton();

    public ICheckBox CreateCheckBox() => new LightCheckBox();
}

public sealed class Dialog
{
    private readonly IUiFactory _factory;

    public Dialog(IUiFactory factory)
    {
        this._factory = factory ?? throw new System.ArgumentNullException(nameof(factory));
    }

    public System.String Compose()
    {
        IButton button = this._factory.CreateButton();
        ICheckBox checkBox = this._factory.CreateCheckBox();
        return button.Render() + checkBox.Render();
    }
}
```

**代价与误用信号**：代价有两面——类与接口数量显著增加；更重要的是扩展方向被锁死：新增一个**产品种类**必须修改抽象工厂接口，从而修改每一个具体工厂（违反开闭原则），而新增一个**变体**只需新增一个具体工厂与一组产品。误用信号：只有一种变体却上了抽象工厂；客户端把工厂创建出的产品再强转回变体具体类型；具体工厂里出现「缺省返回 null」表示不支持该产品种类——那是接口被产品种类绑死的征兆。

**易混辨析**：与工厂方法的区别是产出粒度与扩展方式：抽象工厂返回一族产品且立即返回，工厂方法返回单个产品、以继承作为变化点，抽象工厂通常由一组工厂方法实现。与建造者的区别在于关注点：SourceMaking 的概括是「建造者关注逐步构造一个复杂对象，抽象工厂关注一族产品；建造者在最后一步返回产品，而抽象工厂立即返回产品」。与注册表/服务定位器的区别在于类型安全：抽象工厂的产出在编译期由接口约束，注册表通常返回 `System.Object`。

## 4. 建造者模式 (Builder)

**意图**：将一个复杂对象的构建与它的表示分离，使得同样的构建过程可以创建不同的表示。Refactoring.Guru 的表述是「让你逐步构造复杂对象，并允许用同一段构造代码产出不同类型与表示」。

**适用条件**（可观察的前置条件）：
- 构造参数已经多到出现「伸缩式构造函数」——若干个重载版本互相转发，调用点出现大量 `null`、默认值或占位实参。
- 同一个构造过程需要产出不同的表示（同源数据分别产出对象与文本、报告与图表），步骤相同而每步实现不同。
- 步骤之间存在「可跳过」「可重复」「需延后执行」的差异，而对象本身只应在全部步骤完成后才对外可见。
- 构造过程需要递归或自嵌套地装配一棵复合结构（树、图、嵌套清单）。

**不要用于**：构造参数少于约 4 个、且不存在必填与可选混合的组合时；对象能直接用对象初始化器或一次构造参数表达清楚时。

**角色**：Builder（声明各构造步骤）、ConcreteBuilder（实现这些步骤并保留中间状态、提供取结果的方法）、Product（被构造出的对象，通常应当是构造完成后不可变的）、Director（可选，固定步骤的调用顺序以复用常见配置）、Client（选择具体建造者，必要时把建造者交给指导者驱动）。

**C# 最小实现**：

```csharp
using System;

namespace Acme.Query;

public sealed class Query
{
    private readonly System.Collections.ObjectModel.ReadOnlyCollection<System.String> _columns;

    internal Query(System.String table, System.Collections.Generic.List<System.String> columns)
    {
        this.Table = table;
        // 复制 + ReadOnlyCollection 包装：消费者拿到的 IReadOnlyList 背后是私有副本，
        // 既 cast 不回 List<T>（转换失败），也没有任何可变入口，
        // 因此"至少一列"的校验不会被绕过后再破坏产品。
        this._columns = new System.Collections.ObjectModel.ReadOnlyCollection<System.String>(
            new System.Collections.Generic.List<System.String>(columns));
    }

    public System.String Table { get; }

    public System.Collections.Generic.IReadOnlyList<System.String> Columns => this._columns;
}

public sealed class QueryBuilder
{
    private readonly System.Collections.Generic.List<System.String> _columns = new System.Collections.Generic.List<System.String>();
    private System.String? _table;

    public QueryBuilder From(System.String table)
    {
        this._table = table;
        return this;
    }

    public QueryBuilder Select(System.String column)
    {
        this._columns.Add(column);
        return this;
    }

    public Query Build()
    {
        // 必填约束只能在运行期校验；给不出上下文就无法定位调用点。
        if (this._table is null)
        {
            throw new System.InvalidOperationException("Table 未设置，无法构造 Query。");
        }

        if (this._columns.Count == 0)
        {
            throw new System.InvalidOperationException("至少需要一列，无法构造 Query。");
        }

        return new Query(this._table, this._columns);
    }
}

// 用法：Query query = new QueryBuilder().From("T").Select("A").Build();
```

指导者（Director）只在「同一套步骤顺序需要被多处复用时」才值得存在；它负责顺序，建造者负责每一步的实现，取结果始终由建造者提供。

**代价与误用信号**：代价是引入一个可变的中间对象，且必填字段、字段间一致性这些约束只能推迟到 `Build()` 时才检查——错误从编译期挪到了运行期。误用信号：`Build()` 每次从同一个建造者实例重复取结果而不重置状态（导致上一次的配置泄漏到下一次）；建造者带有耗时副作用或网络调用；为一个只有三个属性且都必填的对象套建造者；把可变集合直接以 `IReadOnlyList<T>` 暴露（消费者可 cast 回 `List<T>` 修改底集合，属于"假不可变"，会绕过 `Build()` 的校验）。

**易混辨析**：与直接用对象初始化器或构造函数加可选参数的区别是可变性——初始化器要求属性可写，建造者可以让产品保持不可变，并把校验集中到唯一出口。与抽象工厂的区别是时序：抽象工厂立即返回产品，建造者允许在取出产品前继续追加步骤。与工厂方法的区别是复杂度目标：工厂方法解决「创建哪一个」，建造者解决「如何一步步装配」。与原型模式的区别是创建起点：建造者从零装配，原型从已有实例复制。

## 5. 原型模式 (Prototype)

**意图**：用原型实例指定创建对象的种类，并通过复制这个原型创建新对象。Refactoring.Guru 的表述是「让你复制已有对象而不使代码依赖它们所属的类」，别名 Clone。SourceMaking 强调它的两个面：把 `new` 表达式里硬编码的类名换成对抽象基类 `clone()` 的调用；以及用一个预配置实例作为后续所有实例的「繁殖者」。

**适用条件**（可观察的前置条件）：
- 初始化成本高（需要解析、查询、计算才能得到一个可用配置），而差异只在少量字段上。
- 代码只持有接口而不知道具体类——例如对象由第三方或运行期插件提供，无法对它调用具体构造函数。
- 需要为同一份复杂配置生成大量仅在细节上不同的变体，为每种组合建子类会退化成子类爆炸。
- 需要保存对象的当前状态副本（快照、撤销、并发分支的初始状态）。

**不要用于**：构造代价低、一次 `new` 的开销可以忽略时；对象含有无法安全浅拷贝的引用字段（句柄、缓存、订阅）而没有对应的深拷贝实现时。

**角色**：Prototype（声明克隆方法）、ConcretePrototype（实现克隆，负责处理引用字段的复制深度）、Client（对抽象原型调用克隆方法）、Prototype Registry（可选，用名字到原型的映射存放常用预配置实例，取用时克隆后返回副本）。

**C# 最小实现**：

```csharp
using System;

namespace Acme.Report;

public sealed record ReportTemplate(
    System.String Title,
    System.String Owner,
    System.Collections.Generic.IReadOnlyList<System.String> Sections);

public static class PrototypeDemo
{
    public static void Run(ReportTemplate baseline)
    {
        // record 的 with 表达式按成员逐字段复制，未列出的成员保持与原对象相同的值。
        // 对引用类型成员而言复制的是引用本身：Sections 仍与原对象共享同一个列表。
        ReportTemplate weekly = baseline with { Title = "周报模板" };

        // 需要独立集合时必须显式重建，否则修改一方会同时影响另一方。
        ReportTemplate detached = baseline with
        {
            Title = "独立副本",
            Sections = new System.Collections.Generic.List<System.String>(baseline.Sections),
        };
    }
}
```

需要显式克隆语义时也可以实现 `System.ICloneable` 并内部调用 `System.Object.MemberwiseClone()`，但必须清楚它的语义：`MemberwiseClone` 创建新对象后逐字段复制，值类型字段按位复制，引用类型字段只复制引用、不复制被引用的对象，因此原对象与克隆体会指向同一个引用对象。文档明确建议：浅拷贝不满足需求时，逐个为引用类型字段赋新对象、或经构造函数重建、或序列化往返。另注意 `System.ICloneable` 的 `Clone()` 返回 `System.Object`，并不承诺浅拷贝还是深拷贝，调用方无法从签名判断。

**代价与误用信号**：代价集中在引用结构上：浅拷贝与深拷贝的区分、循环引用的处理、以及克隆体被误当作独立对象使用。误用信号：只为实现克隆而实现的 `ICloneable` 从不被调用；跨进程或跨序列化边界后仍假设克隆是深拷贝；用序列化往返做深拷贝却不考虑性能与不可序列化成员；为大对象频繁 `Clone()`——那更接近对象池要解决的问题。

**易混辨析**：与工厂方法的区别是创建是否依赖具体类型：工厂方法通过 `new` 具体类型创建，原型通过复制已有实例创建，因此只依赖对象而不依赖类。与拷贝构造函数的区别在于多态：原型由对象自身决定返回哪个具体类型，调用方不需要知道类型。与备忘录模式的区别在意图：原型关心「得到一个等价对象」，备忘录关心「保存并恢复状态」；对结构简单、不含外部资源的对象，克隆常可作为备忘录的轻量替代。

## 6. 对象池模式 (Object Pool)

**意图**：通过复用已初始化的实例来避免反复创建与回收，从而降低成本。SourceMaking 给出的适用条件是三者同时成立：实例初始化成本高、实例化频率高、任一时刻同时在使用中的实例数量低。池通常设计为可增长（池空且未达上限时新建实例），也可以设定最大容量来约束同时借出数。

**适用条件**（可观察的前置条件）：
- 单次构造或获取的成本可测量地高于一次借出/归还的成本（连接建立、非托管缓冲、大型数组）。
- 创建/销毁频率高，而峰值并发持有量明显小于总创建次数。
- 被池化对象没有必须每次重建的外部身份或版本，且它的使用期是短暂的、可明确划分的。
- 存在一个自然的容量上限，超过它时宁可等待或失败，也不应无限增长。

**不要用于**：对象创建廉价、测量不出复用收益时；对象状态无法可靠重置（每次使用都必须沿用上一次的外部身份）时；没有明确的并发或容量约束、池该有多大无从判定时。

**角色**：Reusable（被复用对象，需要能被重置到干净的初始状态）、ReusablePool（持有空闲集合、提供获取与归还，通常还用容量上限约束同时借出数）、Client（借出、使用、归还；必须遵守归还契约）。

**C# 最小实现**：

```csharp
using System;

namespace Acme.Buffers;

public sealed class RentableBuffer
{
    public byte[] Storage { get; } = new byte[64 * 1024];

    // 状态是池化对象的核心风险：Length 只表示"有效长度"，而 Storage 是公开的——
    // 只把 Length 归零，新借出者仍能从 Storage 读到上一个借出者写过的字节。
    public int Length { get; private set; }

    public void Append(byte[] data, int count)
    {
        // 先清掉上一次写入的有效区间，再写入本次数据；否则复用同一实例时旧字节仍留在公开缓冲区里。
        System.Array.Clear(this.Storage, 0, this.Length);
        System.Array.Copy(data, this.Storage, count);
        this.Length = count;
    }

    // 归还路径必须调用：清零本次借出写过的区间，再把有效长度归零。
    public void Reset()
    {
        System.Array.Clear(this.Storage, 0, this.Length);
        this.Length = 0;
    }
}

public sealed class BufferPool
{
    private readonly System.Collections.Generic.Stack<RentableBuffer> _idle =
        new System.Collections.Generic.Stack<RentableBuffer>();

    private readonly int _maxSize;

    // 已借出计数。容量上限约束的是「同时借出数」，而不是空闲栈里堆了几个：
    // 只约束空闲栈的话，池空时仍会无限新建，上限形同虚设。
    private int _leased;

    public BufferPool(int maxSize)
    {
        this._maxSize = maxSize;
    }

    public RentableBuffer Rent()
    {
        lock (this._idle)
        {
            if (this._idle.Count > 0)
            {
                // 空闲栈里有实例，说明它已被归还，同时借出数必然低于上限，直接复用即可。
                System.Threading.Interlocked.Increment(ref this._leased);
                return this._idle.Pop();
            }

            // 池空且同时借出数已达上限时不等待、也不静默超发：抛出可观察的失败，
            // 让容量约束对调用方可见。
            if (System.Threading.Volatile.Read(ref this._leased) >= this._maxSize)
            {
                throw new System.InvalidOperationException("同时借出数已达上限，必须先归还再借出。");
            }

            System.Threading.Interlocked.Increment(ref this._leased);
            return new RentableBuffer();
        }
    }

    public void Return(RentableBuffer buffer)
    {
        System.ArgumentNullException.ThrowIfNull(buffer);
        buffer.Reset();
        lock (this._idle)
        {
            // 归还时递减同时借出数，再把实例压回空闲栈；调用方应把 Return 放在 finally 中。
            System.Threading.Interlocked.Decrement(ref this._leased);
            if (this._idle.Count < this._maxSize)
            {
                this._idle.Push(buffer);
            }
        }
    }
}
```

归还路径必须与异常路径成对：`try/finally`，把 `Return` 放在 `finally` 中。`Return` 先调用 `Reset()` 清零本次写过的数据区间，再递减同时借出数并把实例压回空闲栈；不重置就复用，等于把上一个借用者的数据交给下一个借用者。漏掉一次归还，借出计数就一直偏高，池会提前触到上限并对后续 `Rent()` 抛异常，反复发生即形成池泄漏。

**代价与误用信号**：池把「谁拥有这个对象」的简单答案换成了「谁在什么时候必须归还」的协议，而协议靠约定而非类型系统维持。误用信号：忘记调用 `Reset`，下一个借出者读到脏状态；`Rent()` 成功次数长期大于 `Return()` 次数（借出计数无法回落，池会提前触到上限并对后续 `Rent()` 抛异常，实为泄漏）；把容量上限只加在空闲栈上、借出侧不设限（池空时无限新建，上限形同虚设）；借出对象被放进长期存活的集合（池永远收不回）；池化对象持有外部资源（连接、句柄）而不做有效性检查；为轻量对象上池，测量后发现收益为负。

**易混辨析**：与工厂方法的区别是生命周期管理：工厂方法封装创建逻辑但不跟踪创建出的对象，对象池同时跟踪创建与归还。与享元模式的区别是复用维度：享元复用不可变的共享内部状态、由多个使用方同时读取；对象池复用整个可变实例、任一时刻只被一个使用方持有。与「连接池」的区别在于正确性责任：连接池通常还需承担连接有效性验证、超时回收、心跳淘汰等策略，通用对象池不包含这些。

## 常见误解与反模式

- 为了让依赖「随手可得」而把服务塞进单例：真实依赖被隐藏，构造函数不再说明这个类型需要什么，替换实现与并行测试都变得困难。正确做法是让依赖由构造参数注入，唯一性交给容器或显式的所有权安排。
- 工厂方法写成「一个静态方法 + 类型枚举参数 + `switch`」：这仍是条件分派，只是换了位置，每新增类型都要改这个分支点。需要按类型扩展时应使用多态（子类或注册表），而不是另一次 `if` 链。
- 工厂只包了一层 `new` 而没有抽象产品接口：返回值是具体类型，调用方仍与具体类耦合，多出的层次只增加了跳转成本。
- 抽象工厂只服务一个变体，或把「不支持的产品种类」实现为返回 `null`：前者是过度设计，后者把接口缺陷推迟成调用方的空引用故障。
- 建造者缺少必填校验，或 `Build()` 后不重置状态：前者把「构造出错」变成了下游某个位置的语义错误，后者让上一次的配置泄漏进下一次构造。
- 把浅拷贝当深拷贝使用：`record` 的 `with`、`System.Object.MemberwiseClone()` 都只复制引用类型字段的引用，克隆体与原对象共享同一个子对象，修改会双向可见。
- 引入对象池却没有归还契约（无 `try/finally`、无 `Reset`）：未归还会让借出计数居高不下（设了上限则表现为提前触顶后 `Rent()` 抛异常，没有上限则是缓慢的容量增长），未重置则产生难以复现的脏数据；两者的共同点是出错点与报错点相隔很远，而不是当场失败。
- 把创建型模式当成「依赖注入的替代」：这些模式解决的是「如何得到对象」，不解决「谁负责在何处装配对象」。缺少装配层时，创建逻辑会散落到各个调用点。
