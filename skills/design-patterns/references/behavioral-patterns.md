# 行为型模式 (Behavioral Patterns)

> 本文代码示例的命名空间（`DesignPatterns.Samples.Behavioral`）为示意，不对应 RxToolkits 仓库中的实际类型；示例只演示模式结构，不代表仓库已有同名类型。

## 概览

创建型模式关注"对象怎么产生"，结构型模式关注"对象怎么组合"，行为型模式关注的是**对象之间如何分配职责、如何通信**：一个请求由谁发出、沿什么路径传递、最终由谁执行，以及状态或算法变化时这套通信关系如何不随之崩塌。它们的共同收益是解除发送方与接收方的直接耦合，共同代价是**多出一层间接性**——这层换不来可替换性、可扩展性或可测试性时，就是纯粹的复杂度负债。下表给出一句话意图与最关键代价用于初筛，细节见各节。文中类型名按项目规则 R15 写全限定名（如 `System.String`），以便示例可直接复制编译而无需推断 `using`。

| # | 模式 | 一句话意图 | 最关键的代价/风险 |
| --- | --- | --- | --- |
| 1 | 责任链模式 (Chain of Responsibility) | 让请求沿一条处理者链传递，直到某个处理者处理它，从而解除发送方与接收方的绑定 | 请求可能一路走到链尾都无人处理；没有兜底处理者时表现为静默丢弃 |
| 2 | 命令模式 (Command) | 把请求封装成独立对象，从而支持参数化、排队、记录日志与撤销 | 在调用方与执行方之间多出一整层；命令类数量随操作数线性增长 |
| 3 | 解释器模式 (Interpreter) | 为一种小语言定义文法表示，并用该表示解释语言中的句子 | 只适合简单文法；文法一复杂，类数量爆炸且性能差，应改用手写解析器或解析器生成器 |
| 4 | 迭代器模式 (Iterator) | 顺序访问聚合对象的元素而不暴露其内部表示 | 简单集合上是过度设计；手工实现的迭代器需自行维护失效与版本一致性 |
| 5 | 中介者模式 (Mediator) | 用中介对象封装一组对象的交互，使它们不再互相显式引用 | 中介者会随交互增长演化为上帝对象，成为新的单点复杂度中心 |
| 6 | 备忘录模式 (Memento) | 在不破坏封装的前提下捕获并外部化对象内部状态，以便日后恢复 | 快照会迅速吃掉内存；托管者必须跟踪原发器生命周期并及时废弃过期快照 |
| 7 | 空对象模式 (Null Object) | 用提供"什么都不做"默认行为的可替换对象来封装"对象缺失" | 多出一个类；当"什么都不做"有歧义时需要多个空对象，或说明接口语义不清 |
| 8 | 观察者模式 (Observer) | 定义一对多依赖，使一个对象状态变化时自动通知并更新所有依赖者 | 通知顺序不确定；忘记退订造成内存泄漏；订阅关系本身可能形成环或风暴 |
| 9 | 状态模式 (State) | 让对象在内部状态改变时改变行为，看起来像换了类 | 只少数状态或很少变化时属于过度设计；迁移逻辑分散到各状态类后难以总览 |
| 10 | 策略模式 (Strategy) | 定义一族算法，分别封装并使它们可相互替换 | 调用方必须知道各策略差异才能选择；算法仅两三个且稳定时纯属复杂化 |
| 11 | 模板方法模式 (Template Method) | 在基类定义算法骨架，把某些步骤延迟到子类，而不改变算法结构 | 用继承固定骨架，子类被骨架限制；步骤过多时基类难以维护，且可能违反里氏替换 |
| 12 | 访问者模式 (Visitor) | 在不改变元素类的前提下，为对象结构上的元素定义新操作 | 元素层次一旦新增类，所有访问者都要改动；访问者常需破坏元素封装才能取到数据 |

## 1. 责任链模式 (Chain of Responsibility)

**意图**：使多个对象都有机会处理请求，从而避免请求的发送者与接收者耦合；将这些对象连成一条链，并沿链传递请求，直到有一个对象处理它为止。
**适用条件**（可观察的前置条件）：
- 处理者集合的**数量或顺序在运行时才知道**，或需要运行时增删、重排（不是编译期就能写死的一串 `if`）。
- 同一个请求需要**多个处理者按特定顺序**依次参与，而不是只有一个可能的处理者。
- 发送方**不应该知道**哪个具体对象会处理该请求（写死具体类型等于放弃本模式的全部收益）。
- 存在明确的兜底策略：链尾必须能接住未处理的请求，否则不要用。

**不要用于**：只有一个处理者时（直接调用即可）；请求必须由特定处理者处理、不允许落空时。

**角色**：`Handler`（声明统一处理接口）→ `BaseHandler`（可选，持有 `next` 引用并实现"默认转发给下一个"的样板逻辑）→ `ConcreteHandler`（各自决定"是否处理"与"是否继续传递"）→ `Client`（组装链并把请求交给链上任意一环，不必是队首）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

// 返回 System.Boolean 表示"是否已处理并终止传递"。
// 注意：本例的 false 同时覆盖"被处理者拒绝"与"链尾无人处理"两种情况，
// 调用方无法区分二者；需要区分时应返回三态结果（如 System.Nullable<System.Boolean>
// 或专门的枚举），并让失败路径可观察（项目规则 R11）。
public interface IExpenseApprover
{
    System.Boolean TryApprove(System.Decimal amount, System.String reason);
}

public abstract class ExpenseApproverBase(IExpenseApprover? next) : IExpenseApprover
{
    public System.Boolean TryApprove(System.Decimal amount, System.String reason)
    {
        if (CanApprove(amount)) { return true; }
        // 链条末端没有下一个处理者，返回 false：调用方只能看到"失败"，无从分辨原因。
        return next is not null && next.TryApprove(amount, reason);
    }

    protected abstract System.Boolean CanApprove(System.Decimal amount);
}

public sealed class TeamLeadApprover(IExpenseApprover? next) : ExpenseApproverBase(next)
{
    protected override System.Boolean CanApprove(System.Decimal amount) => amount <= 1_000m;
}

public sealed class DirectorApprover(IExpenseApprover? next) : ExpenseApproverBase(next)
{
    protected override System.Boolean CanApprove(System.Decimal amount) => amount <= 50_000m;
}

public static class ChainDemo
{
    public static void Run()
    {
        IExpenseApprover chain = new TeamLeadApprover(new DirectorApprover(null));
        System.Console.WriteLine(chain.TryApprove(20_000m, "workstation")); // True
        System.Console.WriteLine(chain.TryApprove(99_000m, "datacenter")); // False：无人处理
    }
}
```

**代价与误用信号**：
- 误用信号：链尾没有兜底，请求静默消失——这正是 Refactoring.Guru 列出的唯一缺点（*Some requests may end up unhandled*）。
- 误用信号：链尾的"无人处理"与处理者的"明确拒绝"共用同一个 `false` 返回值，调用方无法分辨（本文件示例即此形态）——失败路径因此不可观察，违反项目规则 R11。需要区分时应返回三态结果，或在链尾写入一次诊断。
- 误用信号：每个请求**只可能由一个**处理者处理，且客户端**已经知道**该由谁处理。SourceMaking 明确建议此时不要用本模式，直接调用更清楚。
- 误用信号：链上处理者之间存在隐含顺序依赖，重排后结果不再正确——说明它们其实是一个不可分割的算法，应改为一个阶段性管线。
- 代价：调试困难。请求在多环之间跳转，调用栈不再反映真实流程，需要每环留一次可观察的命中记录才能定位。

**易混辨析**：与 **装饰器 (Decorator)** 的区别。两者类结构几乎相同（都靠递归组合把执行沿一串对象传递），但意图不同：责任链的处理者可以**各自独立执行任意操作**，并且可以**在任何一点中断**传递；装饰器只能**扩展**对象行为，必须保持基础接口一致，且**不允许打断**请求流。判据：问"这一环能否拒绝继续传递"——能，就是责任链。

## 2. 命令模式 (Command)

**意图**：将一个请求封装为一个对象，从而使你可用不同的请求对客户进行参数化；对请求排队或记录请求日志，以及支持可撤销的操作。
**适用条件**（可观察的前置条件）：
- 需要**把"方法调用"当数据用**：延迟执行、排队、序列化后跨进程发送、写入历史表。
- 同一个操作需要从**多个入口**触发（工具栏、右键菜单、快捷键），而你不愿在三处复制实现。
- 需要**撤销/重做**，且"记录操作"比"记录整个状态"更合适。
- 需要把**一组简单命令组装成复合命令**（宏命令）一次执行。

**不要用于**：命令对象创建后立即执行一次、既不排队也不撤销也不进历史时（那就是换了名字的方法调用）。

**角色**：`Command`（通常只声明一个无参 `Execute()`）→ `ConcreteCommand`（持有接收者引用与全部请求参数，构造时注入）→ `Receiver`（真正干活的业务对象）→ `Invoker/Sender`（持有命令引用并决定何时触发，不负责创建命令）→ `Client`（创建并配置命令，再装配给调用者）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

// Command：返回 System.Boolean 表示是否改变了状态，决定是否进历史。
public interface IEditorCommand
{
    System.Boolean Execute();
    void Undo();
}

// Receiver：真正持有业务状态与业务逻辑。
public sealed class TextEditor
{
    private readonly System.Collections.Generic.List<System.String> _lines = [];
    public void AppendLine(System.String text) => _lines.Add(text);
    public void RemoveLastLine()
    {
        if (_lines.Count > 0) { _lines.RemoveAt(_lines.Count - 1); }
    }
}

public sealed class AppendLineCommand(TextEditor editor, System.String text) : IEditorCommand
{
    public System.Boolean Execute() { editor.AppendLine(text); return true; }
    // 逆操作式撤销：代价是必须为每个命令手写反向逻辑。
    public void Undo() => editor.RemoveLastLine();
}

// Invoker：只认识 IEditorCommand，不认识 TextEditor。
public sealed class CommandInvoker
{
    private readonly System.Collections.Generic.Stack<IEditorCommand> _history = [];

    public void Execute(IEditorCommand command)
    {
        if (command.Execute()) { _history.Push(command); }
    }

    public void UndoLast()
    {
        if (_history.Count > 0) { _history.Pop().Undo(); }
    }
}
```

**代价与误用信号**：
- 误用信号：命令类只是把一次调用原样包装一遍，**永远只被调用一次且不排队、不撤销、不记录**——这是纯粹的间接层，按项目规则 R3 应直接内联。
- 误用信号：命令接口上出现 `Execute()` 的多个重载或大量可选参数——说明请求参数没有固化为字段，用法正退化成"方法调用换了个名字"。
- 代价：类数量随操作数线性增长。Refactoring.Guru 指出它会在发送者与接收者之间引入"一整层"；SourceMaking 的提醒是让命令**不可变**（参数只在构造函数注入），否则历史记录里的命令会被后续调用篡改。
- 撤销有两条路线，各自有代价：**逆操作**（写 `Undo()` 做反向操作）实现难但省内存；**状态快照**（执行前备份状态）实现易但吃内存，且难以覆盖私有状态——后者应交给备忘录模式。

**易混辨析**：与 **策略 (Strategy)** 的区别。两者都能"用一个对象参数化某个动作"，但**意图不同**：策略描述**做同一件事的不同方式**（同一算法的多个变体，由上下文在运行时选定）；命令把一个操作**提升为对象**，目的是**延迟、排队、记录、撤销、远程发送**。判据：问"这个对象需要被存进历史栈或队列吗"——需要就是命令，不需要而只是换算法，就是策略。

## 3. 解释器模式 (Interpreter)

**意图**：给定一个语言，定义它的文法的一种表示，并定义一个解释器，该解释器使用该表示来解释语言中的句子。
**适用条件**（可观察的前置条件）：
- 存在一个**明确定义且反复出现**的领域，其规则可以被表达成"语言"与"句子"（而非一次性的解析需求）。
- 文法**简单且相对稳定**才适用：产生式数量有限、不会持续增长（一旦产生式还在增多，就应改用表驱动解析器或解析器生成器，而不是继续加类），且能映射成"每个产生式一个类"的层次结构。
- 需要**多态地解释**这些句子，且句子会被反复求值，使解释成本可被摊销。
- 你愿意接受 SourceMaking 的第一条检查项：判断"小语言的投入是否值得"。

**不要用于**：文法在持续增长（产生式增多）或语法复杂时（应改用表驱动解析器或解析器生成器）；只需解析固定简单格式时。

**角色**：`AbstractExpression`（声明 `Interpret(Context)`）→ `TerminalExpression`（叶子，如字面量、变量；相同终结符可用享元共享）→ `NonterminalExpression`（复合规则，递归解释子表达式）→ `Context`（封装解析与求值过程中的输入输出状态）→ `Client`（按 Composite 结构组装抽象语法树并触发解释）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

// Context：解释过程中被各表达式读写的共享状态。
public sealed class EvalContext
{
    private readonly System.Collections.Generic.Dictionary<System.String, System.Double> _vars = [];
    public void Set(System.String name, System.Double value) => _vars[name] = value;
    public System.Double Get(System.String name) => _vars[name];
}

public abstract class BoolExpr
{
    public abstract System.Boolean Interpret(EvalContext context);
}

// TerminalExpression：终结符。
public sealed class GreaterThan(System.String name, System.Double threshold) : BoolExpr
{
    public override System.Boolean Interpret(EvalContext context) => context.Get(name) > threshold;
}

// NonterminalExpression：每条文法规则对应一个类，递归解释。
public sealed class AndExpr(BoolExpr left, BoolExpr right) : BoolExpr
{
    public override System.Boolean Interpret(EvalContext context) =>
        left.Interpret(context) && right.Interpret(context);
}

public sealed class NotExpr(BoolExpr inner) : BoolExpr
{
    public override System.Boolean Interpret(EvalContext context) => !inner.Interpret(context);
}

public static class InterpreterDemo
{
    public static void Run()
    {
        // 抽象语法树 = Composite 结构：And(Not(x > 1), y > 2)
        BoolExpr ast = new AndExpr(new NotExpr(new GreaterThan("x", 1d)), new GreaterThan("y", 2d));
        EvalContext context = new();
        context.Set("x", 0.5d);
        context.Set("y", 5d);
        System.Console.WriteLine(ast.Interpret(context)); // True
    }
}
```

**代价与误用信号**：
- 误用信号：文法产生式超过十几条且仍在增长——类数量按产生式数量爆炸，应改用表驱动解析器或解析器生成器。SourceMaking 明确指出：**本模式不解决解析问题**，文法复杂时其他技术更合适。
- 误用信号：为了性能在 `Interpret` 里塞缓存并让表达式变成可变对象——破坏了"表达式是值"的直觉，应先检查表达式树是否被过度复用。
- 代价：每条规则一个类，带来大量细粒度类型；解释是**树遍历**，比编译成中间表示再执行慢得多。
- 注意：SourceMaking 提醒，"基于 Composite 的操作分发"几乎每个 Composite 用例都含解释器形态，但只有当你**真的愿意把该层次视为一门语言**时才叫解释器模式，否则它只是 Composite。

**易混辨析**：与 **组合 (Composite)** 的区别。解释器的抽象语法树**在结构上就是** Composite（SourceMaking 称其 AST 就是一个 Composite，因此迭代器与访问者同样适用），区别在意图：Composite 关注"部分-整体"的统一处理，解释器关注"把层次结构当作语言来求值"。判据：问"这个层次结构是否定义了一门语言"——是，才是解释器。

## 4. 迭代器模式 (Iterator)

**意图**：提供一种方法顺序访问一个聚合对象中的各个元素，而又不暴露该对象的内部表示。
**适用条件**（可观察的前置条件）：
- 集合的**底层结构复杂**（树、图、跳表）而调用方只应看到简单的逐个访问接口。
- 需要**多种遍历方式**（深度优先、广度优先、过滤后遍历），且这些算法不应塞进集合类。
- 需要**多个遍历同时进行**，各自独立记录进度。
- 需要**延迟或暂停遍历**，稍后从同一位置继续。

**不要用于**：集合只是简单数组/`List<T>`、且调用方本来就能接受暴露其结构时；`yield return` 已足够时。

**角色**：`Iterator`（声明取下一个元素、判断是否结束等遍历操作）→ `ConcreteIterator`（自行跟踪遍历进度）→ `Aggregate/Collection`（声明获取迭代器的工厂方法，返回类型必须是迭代器接口）→ `ConcreteAggregate`（返回匹配的具体迭代器实例）→ `Client`（只通过接口使用集合与迭代器，通常不自己 new 迭代器）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

// 在 C# 中，迭代器模式的"接口"就是 BCL 既有的这两个类型：
// System.Collections.Generic.IEnumerable<T> / IEnumerator<T>。
// 因此不必自定义 Iterator 接口，直接用 yield return 实现遍历算法。
public sealed class Tree<T>(T value)
{
    private readonly System.Collections.Generic.List<Tree<T>> _children = [];
    public T Value { get; } = value;

    public Tree<T> Add(T childValue)
    {
        Tree<T> child = new(childValue);
        _children.Add(child);
        return child;
    }

    // 深度优先遍历：遍历算法留在集合内部，对外只暴露标准接口，
    // 调用方看不到 _children。
    public System.Collections.Generic.IEnumerable<T> DepthFirst()
    {
        // 编译器把本方法改写为一个实现了 IEnumerator<T> 的状态机。
        yield return Value;
        foreach (Tree<T> child in _children)
        {
            foreach (T item in child.DepthFirst()) { yield return item; }
        }
    }
}

public static class IteratorDemo
{
    public static void Run()
    {
        Tree<System.String> root = new("root");
        Tree<System.String> a = root.Add("a");
        root.Add("b");
        a.Add("a1");

        // 调用方只依赖 IEnumerable<System.String>，可用 foreach / LINQ。
        foreach (System.String s in root.DepthFirst()) { System.Console.WriteLine(s); }
    }
}
```

**代价与误用信号**：
- 误用信号：为一个 `System.Collections.Generic.List<T>` 字段再包一层自定义迭代器——现代 .NET 的 `foreach` 与 `yield return` 已覆盖绝大多数场景，这是纯增量复杂度（Refactoring.Guru 的缺点条目即"应用该模式对简单集合是过度设计"）。
- 误用信号：手写 `IEnumerator<T>` 时只实现 `MoveNext`，把 `Dispose` 留空或抛异常——`foreach` 提前 `break` 时会调用 `Dispose`，漏掉会泄漏资源。
- 代价：迭代器通常比直接按索引或直接遍历特化集合**更慢**；`yield return` 状态机会分配对象，热路径上需评估。
- 一致性：遍历期间集合被修改时的行为必须明确（BCL 的 `List<T>` 与 `Dictionary<TKey,TValue>` 都选择抛 `System.InvalidOperationException`）。自定义迭代器的版本号校验要显式实现，否则会产生难以复现的错乱结果。

**易混辨析**：与 **访问者 (Visitor)** 的区别。两者都能作用于 Composite 结构，但**职责正交**：迭代器只负责**走到**每个元素（遍历），不对元素做任何业务操作；访问者负责**对**每个元素施加操作，它本身不关心怎么走。判据：问"这个对象是否在决定下一个是谁"——是，就是迭代器。二者经常组合：用迭代器遍历、用访问者施加操作。

## 5. 中介者模式 (Mediator)

**意图**：用一个中介对象来封装一系列的对象交互。中介者使各对象不需要显式地相互引用，从而使其耦合松散，而且可以独立地改变它们之间的交互。
**适用条件**（可观察的前置条件）：
- 一组对象之间存在**多对多**的相互引用，改动其中一个类会牵动一批类（SourceMaking 称之为"意大利面条式代码"）。
- 某个组件**无法在别处复用**，因为它硬编码了对一堆同伴组件的调用。
- 交互规则本身是**可变的业务知识**，应当集中在一处而不是散落在各方。
- 你愿意承担"把交互集中起来"的代价，并接受需要主动防止中介者膨胀为上帝对象。

**不要用于**：只有两方交互时；协调逻辑很少、不会演化时（会退化为上帝对象）。

**角色**：`Mediator`（声明与各组件通信的接口，通常只有 `Notify(sender, event)`）→ `ConcreteMediator`（持有各组件引用并编排它们的协作）→ `Colleague/Component`（只持有中介者接口引用，事件发生时只通知中介者，绝不直接调用同伴）→ `Client`（建立组件与中介者的关联）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

// Mediator：组件只认识这个接口，不认识具体对话框。
public interface IDialogMediator
{
    void Notify(System.Object sender, System.String @event);
}

public abstract class DialogComponent(IDialogMediator mediator)
{
    protected IDialogMediator Mediator { get; } = mediator;
    public System.Boolean Enabled { get; set; } = true;
}

public sealed class DogCheckbox(IDialogMediator mediator) : DialogComponent(mediator)
{
    public System.Boolean Checked { get; private set; }

    public void Toggle()
    {
        Checked = !Checked;
        Mediator.Notify(this, "check");   // 不直接去找文本框
    }
}

public sealed class DogNameTextbox(IDialogMediator mediator) : DialogComponent(mediator)
{
    public System.String Text { get; set; } = System.String.Empty;
}

// ConcreteMediator：组件之间的全部交互规则集中在这里，组件本身保持可复用。
public sealed class DogProfileDialog : IDialogMediator
{
    public DogProfileDialog()
    {
        Checkbox = new DogCheckbox(this);
        Textbox = new DogNameTextbox(this);
    }

    public DogCheckbox Checkbox { get; }
    public DogNameTextbox Textbox { get; }

    public void Notify(System.Object sender, System.String @event)
    {
        if (ReferenceEquals(sender, Checkbox) && @event == "check")
        {
            Textbox.Enabled = Checkbox.Checked;
        }
    }
}
```

**代价与误用信号**：
- 误用信号：中介者里出现按 `sender` 类型分支的巨型 `switch`，或它开始持有与本交互无关的状态——Refactoring.Guru 明确警告：**中介者会随时间演化为上帝对象**。
- 误用信号：组件仍然持有其他组件的具体类型引用（"只在中介者里绕一圈再调回去"）——此时耦合并未消除，只是被隐藏。
- 代价：中介者成为**单点复杂度**与单点故障。SourceMaking 的检查项里直接写着"不要创建控制器或上帝对象"，并提醒要在解耦与职责均摊之间取得平衡。
- 可复用性权衡：SourceMaking 的经验是"**可复用的观察者与主题比可复用的中介者更容易做出来**"。中介者通常与一组具体组件强绑定，跨场景复用率低。

**易混辨析**：与 **观察者 (Observer)** 的区别。SourceMaking 称二者是**竞争模式**：观察者通过引入"主题/观察者"来**分散**通信，一个主题可广播给任意数量、运行时才确定的订阅者；中介者把这些通信**集中封装**进一个对象，组件只知道自己和中介者。Refactoring.Guru 补充：二者可以叠加——中介者常被实现为一个发布者，组件作为订阅者订阅它的事件；此时结构上很像观察者，但意图仍是"消除组件间的相互依赖"。判据：问"协作者是否需要在运行时动态增减，且发布方不关心具体有谁"——是则偏观察者；问"交互规则本身是否是需要集中演进的业务知识"——是则偏中介者。

## 6. 备忘录模式 (Memento)

**意图**：在不破坏封装性的前提下，捕获一个对象的内部状态，并在该对象之外保存这个状态，以便以后可以将该对象恢复到原先保存的状态。
**适用条件**（可观察的前置条件）：
- 需要产生对象状态的**快照**，并能在之后回滚（撤销、事务回滚、检查点）。
- 直接从外部**读取对象私有字段会破坏封装**，因此必须由对象自己产出快照。
- 存在一个明确的**托管者**（历史栈、事务、命令对象）知道"何时"与"为何"存档、何时恢复。
- 快照成本可接受：状态体积有限，或能及时废弃过期快照。

**不要用于**：状态很大且无法负担整体快照时；对象状态本来就可以通过不可变对象整体替换得到时。

**角色**：`Originator`（原发器：知道如何保存自己、如何用快照恢复自己）→ `Memento`（备忘录：镜像原发器状态的值对象，理想上不可变、只有构造函数、无 setter）→ `Caretaker`（托管者：知道何时存档与回滚，**持有但看不到**快照内容）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

public sealed class Editor
{
    // Memento 嵌套在 Originator 内部：私有构造 + 私有成员，
    // 使托管者无法窥视或篡改状态（.NET 支持嵌套类，可走经典实现）。
    public sealed class Snapshot
    {
        private readonly System.String _text;
        private readonly System.Int32 _cursor;

        private Snapshot(System.String text, System.Int32 cursor)
        {
            _text = text;
            _cursor = cursor;
        }

        internal static Snapshot Capture(Editor editor) => new(editor._text, editor._cursor);

        // 唯一能读快照内容的地方：原发器自己。
        internal void Restore(Editor editor)
        {
            editor._text = _text;
            editor._cursor = _cursor;
        }
    }

    private System.String _text = System.String.Empty;
    private System.Int32 _cursor;

    public void Type(System.String text)
    {
        _text += text;
        _cursor = _text.Length;
    }

    public System.String State() => $"{_text} | cursor={_cursor}";
    public Snapshot CreateSnapshot() => Snapshot.Capture(this);
    public void Restore(Snapshot snapshot) => snapshot.Restore(this);
}

// Caretaker：只保存与交还快照，从不读取其内容。
public sealed class History
{
    private readonly System.Collections.Generic.Stack<Editor.Snapshot> _stack = [];
    public void Save(Editor editor) => _stack.Push(editor.CreateSnapshot());

    public void Undo(Editor editor)
    {
        if (_stack.Count > 0) { editor.Restore(_stack.Pop()); }
    }
}
```

**代价与误用信号**：
- 误用信号：托管者开始对 `Snapshot` 做类型判断、读取其属性来决定行为——快照已不再"不透明"，封装被绕过，模式退化为公开 DTO。
- 误用信号：每次按键、每次字段变更都存档——Refactoring.Guru 的首要缺点即**内存占用可能极大**，且托管者必须跟踪原发器生命周期以销毁过期快照。
- 误用信号：把大对象图（含外部连接、文件句柄）整体镜像进快照——恢复时会得到悬空引用；应只保存可重建的状态。
- 语言层面的限制：Refactoring.Guru 指出**在动态语言（PHP/Python/JavaScript）中无法保证备忘录内容不被改动**；在 C# 中应依靠 `private`/`internal` 与不可变值类型达成同样保证，不要依赖约定。

**易混辨析**：与 **命令 (Command)（撤销）** 的区别。SourceMaking 把二者都称为"魔法令牌"，差别在**令牌代表什么**：命令的令牌代表**一个请求**，备忘录的令牌代表**对象在某一时刻的内部状态**。因此命令必须靠多态来执行，而备忘录接口极窄，可以作为值传递。实际实现里二者是配合关系：命令负责执行操作，备忘录负责在执行前保存目标对象的状态（Refactoring.Guru 明确给出这一组合用法）。判据：问"撤销时需要重放一个反向操作，还是需要恢复一份状态"——前者是命令，后者是备忘录。

## 7. 空对象模式 (Null Object)

**意图**：通过提供一个可替换的、具有合适的"什么都不做"默认行为的对象，来封装"对象的缺失"。
**适用条件**（可观察的前置条件）：
- 某处**已经存在**一个协作者协作关系（本模式不引入新的协作，只利用既有的）。
- 某些协作者实例**本就应当什么都不做**，而调用方希望把"什么都不做"和"真的做点什么"一视同仁地对待。
- 你希望把 **null 处理从客户端抽象出去**，消除散落的 `null` 检查。
- "什么都不做"的语义是**唯一确定**的（否则需要多个空对象类，见下）。

**不要用于**：可空引用类型 + `?.`/`??` 已能表达缺省行为时；"空对象"之后还可能变成真实对象时（应改用状态/代理）。

**角色**：`Client`（需要一个协作者）→ `AbstractObject`（声明协作者接口，可为接口提供默认行为）→ `RealObject`（提供 Client 期望的真实行为）→ `NullObject`（接口与 `AbstractObject` 完全一致，但实现为"什么都不做"）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

public interface IAuditSink
{
    void Record(System.String message);
}

public sealed class ConsoleAuditSink : IAuditSink
{
    public void Record(System.String message) => System.Console.WriteLine(message);
}

// NullObject：通常同时是单例——它没有状态，多个实例完全等价。
public sealed class NullAuditSink : IAuditSink
{
    public static readonly NullAuditSink Instance = new();
    private NullAuditSink() { }

    // 方法是空的，但这是语义：空对象要求该成员存在且行为确定。
    public void Record(System.String message) { }
}

public sealed class OrderService(IAuditSink audit)
{
    public void Place(System.String orderId) => audit.Record($"placed {orderId}");
}

public static class NullObjectDemo
{
    public static void Run() =>
        new OrderService(NullAuditSink.Instance).Place("A-1001"); // 注入空对象，而非 null
}
```

**在现代 C# 语境下的取舍（重点）**：**可空引用类型（NRT）加 `?.` / `??` / `??=` 已覆盖绝大多数原本需要 Null Object 的场景**。在启用 `<Nullable>enable</Nullable>` 的 .NET 10 项目中，`IAuditSink? audit` 加上 `audit?.Record(msg)` 既能表达"可能没有"，又能避免空引用异常，代价只有一处 `?.`。因此 **Null Object 只在需要多态默认行为时才值得**：调用点很多且分散、该协作者会作为多态成员被反复调用、或你希望"什么都不做"这一决策由装配方（而非每个调用方）承担。反之，若只是为了省掉三五个 `?.`，引入一个类并不划算——Refactoring.Guru 在 "Introduce Null Object" 中写得很直白：*The price of getting rid of conditionals is creating yet another new class.*

**代价与误用信号**：
- 误用信号：需要**多个** NullObject 类（不同调用方期望不同的"什么都不做"），或需让空对象"在运行时决定怎么什么都不做"——SourceMaking 认为这**通常是 `AbstractObject` 语义接口定义不清的症状**。
- 误用信号：这个"空对象"之后需要**变成真实对象**开始干活。SourceMaking 明确指出：**空对象不会转变为真实对象**；若对象可能从"不做"切换到"做"，它不是空对象，而是带只读模式的真实对象，应当用**状态模式**或**代理模式**（可持有一个空状态或空对象）。
- 代价：多一个类，且行为差异从调用点转移到了装配点——读者需要知道注入了哪个实现才能推断行为，可读性成本从"看到 null 检查"变成"追踪注入来源"。
- 正常无操作 vs 失败路径：`NullAuditSink.Record` 的空方法是**正常语义**，不是需要修掉的"静默失败"——项目规则 R11 约束的是**失败分支**（链尾无人处理、命令未匹配、能力缺失、装配错误）。真正要防的是空对象把"本该发生却没发生"变得不可见（例如审计其实从未接线）：这类必须在**装配点**留下诊断或异常。`IsNull`/`IsNoOp` 之类的显式判据只帮调用点区分，**不能替代** R11 要求的痕迹。

**易混辨析**：与 **可空引用类型 + `?.`/`??`** 的区别。NRT 是**编译器层面的静态检查加调用点短路**，不引入任何类型，不改变多态分派，成本近乎为零，但"什么都不做"这一决策散落在每个调用点，且无法表达"该协作者的默认行为是业务语义的一部分"。Null Object 是**运行时的多态替身**，默认行为集中在一处、可被继承体系和测试替身复用，代价是一个新类。判据：问"这个'什么都不做'是否需要作为多态成员被反复调用、或由装配方统一决定"——是，用 Null Object；否，用 `?.`/`??`。

## 8. 观察者模式 (Observer)

**意图**：定义对象间的一种一对多的依赖关系，当一个对象的状态发生改变时，所有依赖于它的对象都得到通知并被自动更新。
**适用条件**（可观察的前置条件）：
- 状态变化需要触发**其他一组对象**的更新，而这组对象的**实际集合在编译期未知或会动态变化**。
- 需要**运行时建立或解除**对象之间的通知关系（订阅/退订是显式需求，而非内部实现细节）。
- 发布方**不应该知道**订阅者的具体类型（只应依赖订阅者接口）。
- 允许通知顺序不确定，或业务上不依赖通知顺序（Refactoring.Guru 把"订阅者以随机顺序被通知"列为该模式的缺点）。

**不要用于**：通知关系固定且只有一两个接收者时；订阅者生命周期短于发布者又无法可靠退订时。

**角色**：`Publisher/Subject`（持有订阅列表与订阅管理方法，状态变化时广播）→ `Subscriber/Observer`（声明通知接口，通常是单个 `Update`）→ `ConcreteSubscriber`（实现具体响应，所有订阅者实现同一接口）→ `Client`（分别创建发布者与订阅者并完成注册）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

public sealed class PriceChangedEventArgs(System.Decimal price) : System.EventArgs
{
    public System.Decimal Price { get; } = price;
}

public sealed class StockTicker
{
    // 方案 A：C# event。编译器生成 add/remove，退订是订阅方的责任。
    public event System.EventHandler<PriceChangedEventArgs>? PriceChanged;

    public void Update(System.Decimal price) =>
        PriceChanged?.Invoke(this, new PriceChangedEventArgs(price));
}

// 方案 B：显式实现 System.IObserver<T> / IObservable<T>，
// 用于需要"退订令牌"或与其他可观察生态互操作的场景。
public sealed class PriceObserver(System.String name) : System.IObserver<System.Decimal>
{
    public void OnNext(System.Decimal value) => System.Console.WriteLine($"{name} saw {value}");
    public void OnError(System.Exception error) => System.Console.WriteLine($"{name} {error.Message}");
    public void OnCompleted() => System.Console.WriteLine($"{name} done");
}

public static class ObserverDemo
{
    public static void Run()
    {
        StockTicker ticker = new();
        System.EventHandler<PriceChangedEventArgs> handler =
            (_, e) => System.Console.WriteLine($"handler saw {e.Price}");

        ticker.PriceChanged += handler;
        ticker.Update(101.5m);

        // 退订是显式的：不移除就会让 ticker 一直持有 handler 的目标对象。
        ticker.PriceChanged -= handler;
    }
}
```

**`event` / `System.IObserver<T>` 与手工订阅-退订的差别及弱引用需求（重点）**：
- **`event`（方案 A）**：语法最简，`+=` / `-=` 就是订阅与退订。但它本质是**强引用委托链**：发布者存活期间，订阅者的目标对象无法被 GC 回收。若用 lambda 订阅，`-=` 还无法命中（每次都会生成新的委托实例），必须先存成具名委托或方法组——这是"忘记退订导致内存泄漏"最常见的成因。
- **`System.IObserver<T>` / `IObservable<T>`（方案 B）**：接口层面更正式，`Subscribe` 返回 `System.IDisposable`，把"退订"变成**可组合、可 `using` 的一次性动作**，比手工 `-=` 更不容易漏。代价是样板代码更多，且规范要求 `Subscribe` 的返回值必须可安全重复 `Dispose`。
- **手工订阅-退订（自定义 `Attach`/`Detach` 列表）**：只有在需要**弱引用订阅**、**按事件类型分组订阅**或**自定义通知顺序/快照语义**时才值得自己实现。**弱引用需求**正源于第一条：当订阅者的生命周期短于发布者（视图、编辑器窗口、短命服务对象）时，强引用链会让订阅者在视觉上"已经消失"却仍被通知、仍占内存。此时可用 `System.Runtime.CompilerServices.ConditionalWeakTable<TKey,TValue>` 或弱引用委托，但必须同时处理"目标已被回收"的清理路径。
- 无论哪种方案，**订阅与退订必须成对**（对应项目规则 R22 的资源成对纪律），并优先用 `System.IDisposable` 把成对性交给 `using`。

**代价与误用信号**：
- 误用信号：发布者在通知循环中直接遍历**可变**的订阅者集合，而订阅者在回调里退订/订阅——集合被修改导致遍历异常或漏通知。正确做法是先取快照再遍历。
- 误用信号：订阅关系形成环（A 通知 B，B 又通知 A），或通知链路过长导致一次状态更新触发成百次回调（"通知风暴"）。
- 误用信号：同一个订阅者被重复注册多次，收到多份通知；按项目规则 R5，注册点也要有唯一所有者。
- 代价：**顺序不确定**；**异常传播**策略必须明确（一个订阅者抛异常是否中断其余订阅者？需在设计时定下来）。
- 代价：与中介者的边界模糊——两者常互相实现，导致结构难以归类与测试（详见易混模式对照）。

**易混辨析**：与 **中介者 (Mediator)** 的区别。SourceMaking 把二者列为**竞争模式**：观察者**分散**通信（引入"主题"与"观察者"，允许运行时配置多个接收者，通常单向），中介者**集中封装**通信（同组对象的交互规则被抽到一个对象里，通常是双向协议）。Refactoring.Guru 的判据更实用：中介者的首要目标是**消除一组组件之间的相互依赖**，观察者的首要目标是**建立动态的单向连接**；当"所有组件都变成发布者、彼此动态连接"时，就只剩分布式观察者，不再有中心化中介者。

## 9. 状态模式 (State)

**意图**：允许一个对象在其内部状态改变时改变它的行为。对象看起来似乎修改了它的类。
**适用条件**（可观察的前置条件）：
- 对象的**行为是当前状态的函数**，且必须在运行时随状态切换（SourceMaking 的问题陈述即"大量 `case` 语句根据应用状态改变控制流"）。
- **状态数量多、状态相关代码频繁变化**，或某状态的行为需要与其他状态共享大量代码。
- 类里已出现**被状态污染的巨型条件语句**，且同一状态的分支散布在多个方法中。
- 状态之间的**迁移规则本身**是需要被表达的业务知识，而不是隐含在字段赋值里。

**不要用于**：状态只有个位数且极少变化时（`switch` 更短更清楚）；状态之间没有迁移、只是启动参数不同时。

**角色**：`Context`（对外呈现单一接口；持有当前 `State` 引用并把状态相关请求委托给它）→ `State`（声明各状态相关方法；可持有对 Context 的反向引用以获取数据并发起迁移）→ `ConcreteState`（实现本状态的行为，并可决定下一个状态）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

public interface IDocumentState
{
    System.String Name { get; }
    void Publish(Document document);
}

public sealed class Document
{
    private IDocumentState _state = new DraftState();
    public System.Boolean IsAdmin { get; init; }
    public System.String StateName => _state.Name;

    // 迁移的唯一入口：由状态类调用，而不是散落在 Document 各处。
    public void ChangeState(IDocumentState state) => _state = state;
    public void Publish() => _state.Publish(this);
}

public sealed class DraftState : IDocumentState
{
    public System.String Name => "Draft";
    public void Publish(Document document) => document.ChangeState(new ModerationState());
}

public sealed class ModerationState : IDocumentState
{
    public System.String Name => "Moderation";
    // 状态类可以读取 Context，从而基于上下文决定迁移。
    public void Publish(Document document)
    {
        if (document.IsAdmin) { document.ChangeState(new PublishedState()); }
    }
}

public sealed class PublishedState : IDocumentState
{
    public System.String Name => "Published";
    public void Publish(Document document) { }   // 已发布时无操作：这是语义，不是遗漏
}
```

**与"枚举 + `switch`"的取舍（重点）**：SourceMaking 明确指出状态模式针对的正是"以大量 `case` 语句根据状态决定控制流"的问题，并把**表驱动的有限状态机**与**模式驱动**做了对比：表驱动擅长表达**迁移关系**，但难以给迁移附加动作；模式驱动用代码表达迁移，擅长容纳**迁移伴随的动作**。
- 选**枚举 + `switch`**：状态数在**个位数**、迁移规则简单且极少变化、状态行为只影响一两个方法，且你希望整个状态机**能在一个屏幕内读完**。此时 `switch` 是更好的文档，且没有额外类型。
- 选**状态模式**：状态数多或持续增长、每个状态的行为分布在多个方法上、同一状态需要在多处复用，或需要为某些状态提供**默认行为与中间抽象基类**以避免重复代码（Refactoring.Guru 特意提到可用中间抽象类消除状态间重复）。
- Refactoring.Guru 对该模式唯一的缺点条目即：**状态机只有少数几个状态、或很少变化时，应用它是过度设计**。请把这条当作准入判据，而不是事后补救。
- 迁移逻辑放在哪里是一个真实取舍：放在 `Context` 里便于总览但与状态数耦合；放在各 `ConcreteState` 里便于新增状态，但**子类之间产生相互依赖**（SourceMaking 明确指出这一缺点）。

**代价与误用信号**：
- 误用信号：为每个状态的每个方法都写空实现——接口被撑大。Refactoring.Guru 提醒：状态接口里的方法应当**对所有具体状态都有意义**，否则说明接口切分错了。
- 误用信号：状态对象持有大量与状态无关的 Context 数据副本，或状态对象变成有业务主状态的实体——状态应是轻量的（SourceMaking 指出状态对象常实现为单例，配合享元共享）。
- 代价：状态迁移的**全局视图丢失**。相比一张迁移表，分散在各状态类中的 `ChangeState` 调用使"从 A 能到哪些状态"需要翻阅所有类才能回答。
- 注意：SourceMaking 强调状态模式与策略模式**结构相同、意图不同**，且 State 与 Bridge 的结构也完全一致（区别在 Bridge 允许封装体有层次，而 State 只允许一个）。

**易混辨析**：与 **策略 (Strategy)** 的区别。SourceMaking 的判断标准是**意图与绑定时机**：策略是"绑定一次"（bind-once）的选择，选定后算法保持稳定，各策略**互不感知**；状态则更动态，Context 的状态变化会**促使它从自己的"调色板"中重新选择**，且具体状态**可以互相知晓并主动触发迁移**（Refactoring.Guru 表述为 State 不限制具体状态之间的依赖）。判据：问"这些行为对象会不会自己决定换成另一个同类对象"——会，是状态；不会，是策略。

## 10. 策略模式 (Strategy)

**意图**：定义一系列算法，把它们一个个封装起来，并且使它们可相互替换。本模式使得算法可独立于使用它的客户而变化。
**适用条件**（可观察的前置条件）：
- 需要在运行时把一个对象内部的**算法变体**换掉，而调用方不应随之改变。
- 存在**大量相似类，仅在某处行为上不同**，或一个类里有一个持续膨胀的 `switch` 在选择同一算法的不同变体。
- 算法的**实现细节（含其数据与依赖）需要与使用它的业务逻辑隔离**。
- 算法数量**足够多或变化足够频繁**，使"多一个类或一个委托字段"的成本能被摊平。

**不要用于**：算法无状态且只有单一方法签名时（直接传 `System.Func<T>`/委托）；只有一种算法且看不到第二种时。

**角色**：`Context`（持有策略引用，只通过策略接口委派工作；不负责选择算法）→ `Strategy`（声明算法签名）→ `ConcreteStrategy`（实现各变体）→ `Client`（选择并注入具体策略，运行时可通过 setter 替换）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

// 变体 A：显式接口。适合策略有多个方法、需要附带状态或依赖注入。
public interface IShippingCostStrategy
{
    System.Decimal Calculate(System.Decimal weightKg, System.Int32 distanceKm);
}

public sealed class FlatRateShipping : IShippingCostStrategy
{
    public System.Decimal Calculate(System.Decimal weightKg, System.Int32 distanceKm) => 12m;
}

public sealed class WeightBasedShipping : IShippingCostStrategy
{
    public System.Decimal Calculate(System.Decimal weightKg, System.Int32 distanceKm) =>
        5m + (weightKg * 2.5m);
}

public sealed class CheckoutContext(IShippingCostStrategy strategy)
{
    public IShippingCostStrategy Strategy { get; set; } = strategy;
    public System.Decimal Total(System.Decimal weightKg, System.Int32 distanceKm) =>
        Strategy.Calculate(weightKg, distanceKm);
}

// 变体 B：委托。当策略只有一个方法、无状态、也不需要独立依赖时，
// System.Func<> 可以直接替代整个接口层次，省掉 N 个类。
public sealed class CheckoutWithDelegate(System.Func<System.Decimal, System.Int32, System.Decimal> strategy)
{
    public System.Func<System.Decimal, System.Int32, System.Decimal> Strategy { get; set; } = strategy;

    public System.Decimal Total(System.Decimal weightKg, System.Int32 distanceKm) =>
        Strategy(weightKg, distanceKm);
}

public static class StrategyDemo
{
    public static void Run()
    {
        CheckoutContext a = new(new FlatRateShipping());
        // 委托版：重量 + 距离计费，两个参数都被用到，且无需新建类。
        CheckoutWithDelegate b = new((w, d) => 5m + (w * 2.5m) + (d * 0.01m));
        System.Console.WriteLine(a.Total(3m, 100) + b.Total(3m, 100));
    }
}
```

**委托 / `System.Func<T>` 何时可直接替代接口（重点）**：Refactoring.Guru 在 Strategy 的缺点里专门列了一条：许多现代语言支持函数类型，可以用一组匿名函数实现算法的不同版本，**像使用策略对象一样使用这些函数，而不必用额外的类与接口把代码撑大**。取舍如下：
- **可以直接用 `System.Func<T…, TResult>`**：策略只有**一个**方法；无自有状态（或状态已由闭包捕获）；不需要独立的依赖注入；不需要在运行时按类型查找或替换；不需要对它做基于接口的测试替身。
- **仍应保留接口**：策略有**两个及以上**相关方法（如 `Validate` + `Apply`，它们必须一致变化）；策略持有会变化的内部状态；策略需要由 DI 容器按生命周期解析；需要以类型为键注册多个策略（`System.Collections.Generic.IReadOnlyDictionary<System.String, IShippingCostStrategy>`）；需要给调用方一个可被 mock 的接缝。
- 一条可操作的判据：**把委托换成接口时，是否会产出一批只有单个方法、且从未被单独引用的类**（对应项目规则 R3 判定的"无用层"）？如果是，就先别急着建接口。
- 注意：`System.Func<T>` 参数增多后可读性急剧下降（`Func<decimal,int,string,bool,decimal>` 无法自解释）；超过三个参数就应考虑引入具名的请求记录类型或回到接口。

**代价与误用信号**：
- 误用信号：只有一个策略实现，且没有任何替换需求——直接把算法内联进 Context。
- 误用信号：Context 里出现 `if (strategy is WeightBasedShipping s)`——说明 Context 开始认识具体策略，抽象漏了。
- 误用信号：Client 需要读策略内部状态才能决定选哪个——Refactoring.Guru 的缺点条目即"**客户端必须了解各策略之间的差异才能选对**"。若这个选择逻辑本身复杂，考虑把它提升为一个工厂或一个选择策略。
- 代价：策略与 Context 之间需要建立数据传递协议。策略若需要 Context 的大量数据，要么 Context 传自己进去（双向耦合），要么在接口上堆长参数列表——这两种都会侵蚀模式的收益。

**易混辨析**：与 **模板方法 (Template Method)** 的区别。SourceMaking 的概括最精炼："策略与模板方法除**粒度**外相似"：模板方法用**继承**改变算法的**一部分**，策略用**委托**改变**整个**算法。Refactoring.Guru 补充了作用域差异：模板方法作用在**类级别**（静态，编译期确定骨架），策略作用在**对象级别**（运行时替换行为）。判据：问"变化点是否需要每实例独立，并且要在运行时切换"——是，用策略（组合）；否，且差异天然对应子类，用模板方法（继承）。

## 11. 模板方法模式 (Template Method)

**意图**：定义一个操作中的算法的骨架，而将一些步骤延迟到子类中。模板方法使得子类可以不改变一个算法的结构即可重定义该算法的某些特定步骤。
**适用条件**（可观察的前置条件）：
- 多个类包含**几乎相同**的算法，只在少数步骤上有差异，而每次算法变化都要改所有这些类。
- 算法的**不变部分是稳定的**，且**步骤顺序本身是必须被强制的约束**（不允许子类改变结构）。
- 需要为框架或库留出**受控的扩展点**，且扩展方式是"继承基类"（SourceMaking 称之为"好莱坞原则"：*don't call us, we'll call you*）。
- 差异天然对应"是一种"关系，而不是"用某个可替换部件"关系。

**不要用于**：步骤顺序不需要被强制、或变化点在运行期才决定时（那用组合/策略）；子类需要改动的步骤很多、骨架已不再是一个算法时。

**角色**：`AbstractClass`（声明 `TemplateMethod()` 及组成算法骨架的各步骤方法；步骤可以是抽象方法、带默认实现的可选步骤、或空实现的钩子）→ `ConcreteClass`（必须实现全部抽象步骤，可选地覆写部分可选步骤；**不得覆写模板方法本身**）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

public abstract class DataImporter
{
    // 模板方法：骨架 + 步骤顺序。非 virtual，防止子类破坏结构。
    public void Import(System.String path)
    {
        Open(path);
        // 释放必须由骨架保证：异常路径下 Close() 也要执行（项目规则 R22）。
        // Open() 在 try 之外——它失败时没有已获取的资源需要释放。
        try
        {
            Parse();
            BeforeAnalyze();      // 钩子：默认空实现，可选覆写
            Analyze();
            Report();
        }
        finally
        {
            Close();
        }
    }

    protected abstract void Open(System.String path);
    protected abstract void Parse();

    // 可选步骤：有合理默认实现，子类按需覆写。
    protected virtual void Analyze() => System.Console.WriteLine("default analyze");
    protected virtual void Report() => System.Console.WriteLine("default report");

    // 钩子：空实现，不覆写模板方法也能正常工作。
    protected virtual void BeforeAnalyze() { }

    protected abstract void Close();
}

public sealed class CsvImporter : DataImporter
{
    protected override void Open(System.String path) => System.Console.WriteLine($"open csv {path}");
    protected override void Parse() => System.Console.WriteLine("parse csv rows");
    protected override void Close() => System.Console.WriteLine("close csv");
}
```

**代价与误用信号**：
- 误用信号：**钩子过多**，基类里有七八个 `virtual` 空方法——骨架不再表达一个算法，而退化成一个事件列表；子类作者无法判断哪些必须覆写、哪些可以忽略。经验界限：抽象步骤、可选步骤与钩子合计超过 5 个时应重新审视算法是否被正确切分。
- 误用信号：子类覆写了一个步骤却**故意让它什么都不做**，以"取消"基类的默认行为——Refactoring.Guru 明确警告这可能**违反里氏替换原则**（*violate the Liskov Substitution Principle by suppressing a default step implementation via a subclass*）。若"取消"是合法语义，应把该步骤改成钩子或引入显式的策略开关，而不是靠空覆写。
- 误用信号：模板方法本身被声明为 `virtual`/`abstract`，子类可以改变步骤顺序——骨架的强制力随之消失。
- 代价：**用继承换来的强制力同时是限制**。Refactoring.Guru 的首条缺点即"**客户端可能被提供的算法骨架限制住**"；此外"模板方法的步骤越多越难维护"。继承是编译期绑定，无法按实例替换（这点与策略相反）。
- 资源纪律：若不使用 `try`/`finally`，异常路径下 `Close()` 不会执行——这是模板方法骨架里最容易漏掉的资源纪律（项目规则 R22）。释放必须由骨架的 `try`/`finally` 保证，模板方法只负责业务顺序（本文件示例即此形态）。

**易混辨析**：与 **策略 (Strategy)** 的区别。SourceMaking 的规则是："模板方法用**继承**来变化算法的一部分，策略用**委托**来变化整个算法"；"策略修改单个对象的逻辑，模板方法修改整个类的逻辑"。Refactoring.Guru 的补充是绑定时机：模板方法在**类级别、静态**，策略在**对象级别、可运行时切换**。判据：问"变化点是否需要按实例不同、且运行时可换"——需要就用组合（策略）；若差异稳固地对应子类且顺序必须被强制，则用继承（模板方法）。

## 12. 访问者模式 (Visitor)

**意图**：表示一个作用于某对象结构中的各元素的操作。它使你可以在不改变各元素的类的前提下定义作用于这些元素的新操作。
**适用条件**（可观察的前置条件）：
- **元素类层次是稳定的**（类很少新增），而**需要施加的操作是变化的**——这是本模式成立的唯一根本前提。SourceMaking 的检查项第一条即"确认当前 Element 层次将相当稳定"。
- 需要在一个**异构的复杂对象结构**（如 Composite 树）上执行操作，且操作需要按元素的具体类型区分行为。
- 不想把与元素本职无关的操作**污染进元素类**（例如给地理数据节点加 XML 导出）。
- 元素类的公开接口**足以支撑**访问者所需的数据访问；或你能接受为访问者开放必要成员。

**不要用于**：元素类型层次还在增长时（每加一个元素类都要改所有访问者）；元素必须守住封装、无法为访问者开放内部数据时。

**角色**：`Visitor`（为每个具体元素类声明一个 `Visit` 重载）→ `ConcreteVisitor`（为每个元素类实现对应行为，可在遍历过程中累积状态）→ `Element`（声明 `Accept(Visitor)`）→ `ConcreteElement`（`Accept` 实现固定为把 `this` 转交出去：`visitor.Visit(this)`，**所有子类都必须覆写**，不能靠基类继承，因为基类里的 `this` 静态类型是基类）→ `Client`（创建访问者并把它交给元素）。
**C# 最小实现**：
```csharp
namespace DesignPatterns.Samples.Behavioral;

public interface IShapeVisitor
{
    void Visit(Circle circle);
    void Visit(Rectangle rectangle);
}

public interface IShape
{
    void Accept(IShapeVisitor visitor);
}

public sealed class Circle(System.Double radius) : IShape
{
    public System.Double Radius { get; } = radius;
    // 第一次分派：确定元素的动态类型。
    public void Accept(IShapeVisitor visitor) => visitor.Visit(this);
}

public sealed class Rectangle(System.Double width, System.Double height) : IShape
{
    public System.Double Width { get; } = width;
    public System.Double Height { get; } = height;
    public void Accept(IShapeVisitor visitor) => visitor.Visit(this);
}

// ConcreteVisitor：可以在遍历过程中累积状态。
public sealed class AreaVisitor : IShapeVisitor
{
    public System.Double Total { get; private set; }

    // 第二次分派：重载在编译期由 this 的静态类型确定，
    // 元素类型在运行期确定 —— 二者合起来即双重分派。
    public void Visit(Circle circle) => Total += System.Math.PI * circle.Radius * circle.Radius;
    public void Visit(Rectangle rectangle) => Total += rectangle.Width * rectangle.Height;
}

public static class VisitorDemo
{
    public static void Run()
    {
        System.Collections.Generic.List<IShape> shapes = [new Circle(1d), new Rectangle(2d, 3d)];
        AreaVisitor visitor = new();
        foreach (IShape shape in shapes) { shape.Accept(visitor); }
        System.Console.WriteLine(visitor.Total);
    }
}
```

**双重分派要点**：C# 的方法重载是**编译期**按参数的静态类型解析的。若写成 `foreach (IShape s in shapes) { visitor.Visit(s); }`（不走 `Accept`），重载解析只会选中基类型版本，元素的具体类型信息在"恢复"过程中丢失。`Accept(visitor) => visitor.Visit(this)` 之所以有效，是因为在 `Circle` 类体内的 `this` **静态类型就是 `Circle`**，把类型判定责任交给元素自己，从而避开一长串 `is` 与强制转换。

**代价与误用信号**：
- 误用信号：**元素层次还在增长**。每新增一个元素类，`Visitor` 接口与**所有**已有具体访问者都必须修改——Refactoring.Guru 的首条缺点即此；SourceMaking 更直接："如果聚合节点层次不稳定，保持访问者子类同步需要极大的努力"。
- 误用信号：访问者为了取到数据开始读取元素的私有字段，或迫使元素公开大量内部成员——Refactoring.Guru 明确把"**访问者可能无法访问元素所需的私有字段与方法**"列为缺点。这是**访问者破坏封装**的典型形态：元素类的封装被为了外部算法而打开。
- 误用信号：元素层次不稳定的同时访问者层次也不稳定（两边都在变）——此时应考虑**交换两个层次的角色**（SourceMaking 检查项第 4 条给出的正是这一处置），或干脆把操作放回元素类。
- 代价：访问者是"**一道回归到函数式分解的门**"——把算法从数据结构中分离出去，这与面向对象的直觉相反。SourceMaking 承认这一批评的合理性，并给出辩护视角：它把非传统行为提升为完整的对象。
- 代价：需要双向的类型耦合——元素层次只耦合到访问者基类，但访问者层次耦合到**每一个**具体元素类（SourceMaking 明确指出这一点）。这使访问者难以作为通用库发布。

**易混辨析**：与 **迭代器 (Iterator)** 的区别。SourceMaking 的对照最清晰："**迭代器遍历 Composite，访问者对 Composite 施加操作**"。二者职责正交且常组合：迭代器只解决"下一个元素是谁"，不碰业务语义；访问者只解决"对这类元素做什么"，不关心遍历路径。Refactoring.Guru 也建议把 Visitor 与 Iterator 一起用于遍历复杂结构并对不同类的元素施加操作。判据：问"这个对象是否在按元素类型分派行为"——是，就是访问者。

## 易混模式对照

| 模式 A | 模式 B | 判别问题 |
| --- | --- | --- |
| 策略 (Strategy) | 状态 (State) | 这些行为对象会不会**自己决定切换**成另一个同类对象？会互相知晓并触发迁移的是状态；只由外部选定一次、彼此无感知的是策略。 |
| 策略 (Strategy) | 命令 (Command) | 这个对象需要被**存进队列或历史栈**、延迟执行、撤销或跨进程发送吗？需要是命令（令牌代表一个请求）；只是"做同一件事的不同方式"是策略。 |
| 责任链 (Chain of Responsibility) | 装饰器 (Decorator) | 这一环**能否拒绝继续传递**、或独立做一件与前后无关的事？能则是责任链；只能扩展行为、必须保持接口一致且不得打断请求流的是装饰器。 |
| 观察者 (Observer) | 中介者 (Mediator) | 通信是**分散**给运行时动态增减的订阅者（发布方不关心有谁），还是把交互规则**集中**封装进一个对象？前者观察者，后者中介者。 |
| 模板方法 (Template Method) | 策略 (Strategy) | 可变部分需要**按实例不同并在运行时替换**吗？需要则用组合（策略，作用于对象级别）；若差异稳固对应子类且步骤顺序必须被强制，则用继承（模板方法，作用于类级别）。 |
| 访问者 (Visitor) | 迭代器 (Iterator) | 这个对象是在决定"**下一个是谁**"（遍历），还是在决定"**对这类元素做什么**"（按类型分派操作）？前者迭代器，后者访问者；二者可组合。 |
| 备忘录 (Memento) | 命令 (Command)（撤销） | 撤销时是**恢复一份状态快照**，还是**重放一个反向操作**？快照是备忘录（令牌代表状态，可作值传递）；反向操作是命令（令牌代表请求，依赖多态）。 |
| 空对象 (Null Object) | 可空引用类型 + `?.`/`??` | 这个"什么都不做"是否需要作为**多态成员被反复调用**，或应由**装配方统一决定**？是则值得一个空对象类；若只是为了省掉三五个 `?.`，用可空引用类型即可（且该模式要求"空对象永远不变为真实对象"）。 |
| 解释器 (Interpreter) | 组合 (Composite) | 这个层次结构是否被当作**一门语言**来求值？是则解释器（AST 在结构上就是 Composite，因此迭代器与访问者同样适用）；只是"部分-整体"统一处理则是 Composite。 |
| 状态 (State) | 枚举 + `switch` | 状态数是否仍在**增长**、状态相关代码是否**频繁变化**、同一状态的行为是否散布在多个方法中？任一为是则值得**考虑**状态模式；状态只有个位数且极少变化时，`switch` 是更好的文档。这三条是**信号**而非准入条件，与 `pattern-selection.md` 的检查信号表同一口径。 |

## 常见误解与反模式

（各模式自身的误用信号见对应条目的「代价与误用信号」；本节只列跨模式的共性红线。）

- **模式先行**：先说出"这里要用策略模式"，再回头去寻找变化点与症状，于是为一个并不存在的第二种实现预留了扩展点。正确顺序是先写下"变化的轴是什么、谁不该知道谁、现在最难受的具体位置在哪"；三条都写不出，就说明还没有已出现的问题。
- **一次性抽象**：新增的接口、基类或抽象步骤只有唯一实现加唯一调用点（违反项目规则 R3）。判据是删除测试——删掉一半新增类型后行为不变，说明另一半只是间接层；行为型模式里这类层最常见的来源是"以后可能要替换"。
- **抽象通货膨胀**：一次功能改动引入 5 个以上新类型，或新增类型数与要解决的问题规模明显不相称。行为型模式的类型数量通常沿变化轴线性增长，一旦超过变化轴本身的规模，就应退回更简单的分解（内联、`switch`、`yield return`、`System.Func<T>` 等语言特性）。
- **靠类图而不是意图区分模式**：行为型模式里有多组结构几乎逐字相同的模式（策略/状态、责任链/装饰器、中介者/观察者、命令/备忘录）。只比较类型结构必然选错，必须回到"谁在什么时机决定行为、这个对象是否需要被存储或重放"这一意图层面判断。
