#!/usr/bin/env python3
"""check-consistency.py —— 全局规则 vs agent 文件 / 指南 的一致性检查。

用途
----
同一套规则写在四处（全局 AGENTS.md、四个 agents/*.toml、配置指南）。
改一处忘改另一处，就会出现「全局说 A、agent 说 B」——子代理按 B 执行，
全局规则的保护被抵消。

本脚本把这类规则登记成表，一条命令扫出所有不一致。

用法
----
    python -X utf8 check-consistency.py            # 只报问题
    python -X utf8 check-consistency.py -v         # 详细
    python -X utf8 check-consistency.py --only 测试量

退出码：0 = 一致；1 = 发现不一致（可接 CI 或提交前钩子）

设计要点
--------
1. 「已作废说法」不能简单搜字符串——它合法地出现在**禁止清单**、
   **历史注记**、**对比表**里。所以每条 deprecate 规则都带 `guard`：
   命中行附近出现守卫词（never/superseded/已废弃…）时视为合法引用。
2. 「必需说法」检查的是**存在性**：全局有、agent 也该有。
3. 本脚本只读，不改任何文件。
"""
from __future__ import annotations

import argparse
import datetime
import io
import os
import re
import sys
import tomllib
from dataclasses import dataclass, field

HOME = os.path.expanduser("~")
CODEX = os.path.join(HOME, ".codex")
AGENTS_DIR = os.path.join(CODEX, "agents")
GLOBAL_MD = os.path.join(CODEX, "AGENTS.md")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(REPO, "docs", "CODEX-SETUP.md")
TEMPLATES = os.path.join(REPO, "docs", "CODEX-AGENTS-TEMPLATES.md")

AGENT_NAMES = ("architect", "mech", "explorer", "verifier", "committer")

def find_hits(txt: str, pattern: str, allow_markers: list[str]) -> list[str]:
    """找出旧说法的真实命中。

    不做上下文猜测——早期版本靠"附近有没有 never/do not"判断是否为合法引用，
    实测两次误判（"Avoid it:" 与块引用里另一条禁令的 "do not"），
    结果是把真实不一致当成合法引用放过了。

    现在改为**显式豁免**：只有当命中所在行含有本规则声明的 allow_markers
    （例如"(superseded)"、"— see 7.12"）时才跳过。宁可多报，不可漏报：
    多报只是噪音，漏报会让全局规则被 agent 文件覆盖。
    """
    out = []
    for m in re.finditer(pattern, txt, re.I):
        line_start = txt.rfind("\n", 0, m.start()) + 1
        line_end = txt.find("\n", m.end())
        line = txt[line_start:line_end if line_end > 0 else len(txt)]
        if any(a.lower() in line.lower() for a in allow_markers):
            continue
        out.append(m.group(0)[:70])
    return out


@dataclass
class Rule:
    """一条跨文件规则。"""
    key: str                      # 唯一标识
    title: str                    # 中文说明
    required: list[str]           # 必须出现的说法（小写子串）
    applies_to: tuple[str, ...]   # 哪些文件必须有：global/agent:<name>/guide
    require_all: bool = False     # True=全部命中；False=任一命中即可
    deprecate: list[str] = field(default_factory=list)  # 不得出现的旧说法（正则）
    allow: list[str] = field(default_factory=list)      # 该行含这些标记时视为合法引用
    why: str = ""                 # 为什么这条重要
    scoped_required: dict[str, list[str]] = field(default_factory=dict)  # 按 scope 覆盖 required


RULES: list[Rule] = [
    Rule(
        key="test-volume",
        title="测试量规则",
        required=["review signal", "behaviour coverage"],
        applies_to=("global", "agent:architect", "guide"),
        require_all=True,
        deprecate=[
            r"cut it back",
            r"more test lines than implementation",
            r"one test case per ten",
            r"keep tests proportionate",
            r"leave the combinatorial explosion alone",
            r"不得超实现行数",
        ],
        allow=["(superseded)", "已废弃", "已作废", "早期", "历史"],
        why="按比例删测试会抵消行为覆盖；比例只能触发复查。",
    ),
    Rule(
        key="sandbox-modes",
        title="沙箱模式数量",
        required=["three sandbox modes", "danger-full-access"],
        applies_to=("global", "guide"),
        deprecate=[r"only two sandbox modes", r"has only two modes", r"只有两种模式"],
        allow=["(superseded)", "superseded", "已废弃", "已作废", "已被 §7"],
        why="Codex 有三种模式；说成两种会误导读者以为 danger-full-access 不存在。",
    ),
    Rule(
        key="network-default",
        title="网络默认值",
        required=["command network access", "deliberately"],
        applies_to=("global", "guide"),
        deprecate=[
            r"sandbox does not disable network access by default",
            r"is the sandbox default",
        ],
        allow=["(superseded)", "已废弃", "已作废", "早期"],
        why="官方默认是关闭；写成默认开启会让人误判风险。",
    ),
    Rule(
        key="design-ownership",
        title="设计归属",
        required=["do not make design decisions"],
        applies_to=("agent:architect",),
        deprecate=[
            r"you own the design",
            r"design decisions within an assigned slice",
            r"settles the design for a slice and then implements",
        ],
        allow=["(superseded)", "已废弃", "已作废", "早期"],
        why="设计归主线程；architect 只实现已定设计。",
    ),
    Rule(
        key="worktree-boundary",
        title="worktree 边界措辞",
        required=["working-copy isolation"],
        applies_to=("global",),
        deprecate=[
            r"genuinely hard boundary",
            r"isolated from the primary workspace by construction",
        ],
        allow=["(superseded)", "已废弃", "已作废", "早期"],
        why="目录分离只是工作副本隔离，不是安全边界。",
    ),
    Rule(
        key="observation-vs-advice",
        title="观察 vs 建议",
        required=["report observations, never advice"],
        applies_to=("agent:architect", "agent:mech", "agent:explorer", "agent:verifier"),
        deprecate=[r"feel free to suggest", r"you may recommend"],
        why="禁的是建议，不是信息；阻塞与带指向的观察必须上报。",
    ),
    Rule(
        key="contract-shapes",
        title="契约形状",
        required=["rule brief", "question brief", "full brief"],
        applies_to=("global",),
        require_all=True,
        deprecate=[r"none may be omitted"],
        allow=["(superseded)", "已废弃", "已作废", "早期"],
        why="契约按执行者职责裁剪；一刀切 12 字段对简单任务是纯开销。",
    ),
    Rule(
        key="delegation-decision-content",
        title="委派决策内容保留，收益描述移除",
        # 决策内容必须在：硬性否决、六问、预算、派给谁、校准
        required=["Hard negatives", "six questions", "Budget", "Which agent", "Calibration"],
        applies_to=("global",),
        require_all=True,
        # 收益描述不得回来：成本表、收益表、收益问句、交易vs门槛
        deprecate=[r"Delegation is a trade",
                   r"net-benefit test",
                   r"Would delegating save",
                   r"costs, and they are paid",
                   r"at `xhigh` prices"],
        allow=["(superseded)", "已废弃", "早期"],
        why="决策内容（硬性否决/六问/预算/查表/校准）是判断依据，必须保留；"
            "成本表、收益表与「省下的多于花掉的」这类收益描述已移除。",
    ),
    Rule(
        key="readonly-brief",
        title="只读/机械 agent 知道收到短契约",
        required=["the brief you receive is short"],
        applies_to=("agent:mech", "agent:explorer"),
        why="否则它们会把精简契约当成 brief 不完整而误报 blocked。",
    ),
    Rule(
        key="scope-statement",
        title="文档范围声明",
        required=["调度决策", "不含"],
        applies_to=("guide",),
        require_all=True,
        # 声明里不得再出现与实际内容矛盾的排除项
        deprecate=[r"不含收益分析", r"不含性能数据"],
        why="开头声明「不含收益分析」会误导读者，而文档已含完整的委派收益判断体系。",
    ),
    Rule(
        key="guide-version",
        title="指南版本日期不早于最后修改",
        # 存在性由本规则检查；日期比较在 check_guide_version 中做（看 live 配置的 mtime）
        required=["**版本**"],
        applies_to=("guide",),
        why="版本日期落后于内容会让读者以为是旧版。",
    ),
    Rule(
        key="acceptance-ambiguity",
        title="验收措辞不歧义",
        required=["final accept/reject decision", "does not ban the `[Acceptance]` field"],
        applies_to=("global",),
        require_all=True,
        deprecate=[r"Acceptance or credentials are involved",
                   r"涉及验收或凭据"],
        allow=["(superseded)", "已废弃", "早期"],
        why="说成「涉及验收就不派」会被字面读成禁止所有 architect 委派；"
            "禁的是最终决策权，不是 brief 里的验收标准。",
    ),
    Rule(
        key="template-copyable",
        title="配置模板可直接保存使用",
        required=["本文件可以直接保存使用", "已注释"],
        applies_to=("guide",),
        require_all=True,
        # 不得再声称"需替换"（那是"改完才可用"，不是可直接使用）
        deprecate=[r"尖括号占位符需替换为你自己的值"],
        allow=["(superseded)", "已废弃", "早期"],
        why="模板里有未注释的占位符时，直接复制会写进一份无效配置；"
            "依赖个人路径的段落应注释掉，并说明可直接保存。",
    ),
    Rule(
        key="guide-sync-entry",
        title="指南指向同步入口",
        required=["sync-config.ps1"],
        applies_to=("global",),
        deprecate=[r"by hand and hope"],
        why="改了配置不同步，子代理会按旧规则执行；必须有明确入口。",
    ),
    Rule(
        key="size-metric",
        title="规模只作信号，不作指标",
        required=["Never aim at a size", "measure executable lines"],
        applies_to=("global",),
        require_all=True,
        # 这些措辞把行数/文件数变成了可执行的门限
        deprecate=[r"more than about a dozen files",
                   r"no file exceeds N lines",
                   r"lines of code limit",
                   r"under \d+ lines per (file|method)"],
        allow=["(superseded)", "已废弃", "早期"],
        why="行数一旦成为指标，最省事的达标方式就是压行、删注释、拆碎，直接损害可读性；"
            "且文件行数含空行与注释，不代表逻辑量。",
    ),
    Rule(
        key="no-line-budget",
        title="agent 文件不得设行数上限",
        required=["line budget"],
        applies_to=("agent:architect",),
        deprecate=[r"no file exceeds N lines",
                   r"exceeds N lines",
                   r"under N lines"],
        allow=["(superseded)", "已废弃", "早期"],
        why="把行数写成上限会诱导压行、删注释、拆碎文件，直接损害可读性。",
    ),
    Rule(
        key="verdict-taxonomy",
        title="状态判定三分",
        required=["decided by cause"],
        applies_to=("global",),
        deprecate=[r"without command output it must be\n?\s*`?unverified`?\.?\*?\*?$"],
        allow=["(superseded)", "已废弃", "已作废", "早期"],
        why="failed/blocked/unverified 按成因判，不能一律 unverified。",
    ),
    Rule(
        key="commit-gate",
        title="提交门禁",
        required=["Every commit goes through", "Commit brief", "diff gate",
                  "gate applicability", "not required", "S0", "S1"],
        applies_to=("global",),
        require_all=True,
        deprecate=[r"main thread commits", r"main thread may commit"],
        allow=["(superseded)", "已废弃", "已作废", "早期"],
        why="提交是最后一道门；主线程直接提交会绕开 committer 的 diff 分级。",
    ),
    Rule(
        key="committer-audit",
        title="committer 定义与档位",
        required=["`committer` | `gpt-6.1-sol` @ `medium`"],
        applies_to=("global", "agent:committer"),
        require_all=True,
        scoped_required={
            "agent:committer": ["verdict", "S0", "S1", "risk_findings",
                                "must not modify source", "out_of_scope",
                                "gate_applicability", "not required"],
        },
        why="Roles 表必须按 medium 档登记 committer；正文缺审计字段则分级与门禁无法执行。",
    ),
]


def read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    return io.open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def load_sources() -> dict[str, str]:
    src = {"global": read_text(GLOBAL_MD), "guide": read_text(GUIDE),
           "templates": read_text(TEMPLATES)}
    for n in AGENT_NAMES:
        p = os.path.join(AGENTS_DIR, n + ".toml")
        try:
            j = tomllib.loads(read_text(p))
            src[f"agent:{n}"] = j.get("developer_instructions", "")
        except Exception as e:  # noqa: BLE001
            src[f"agent:{n}"] = ""
            print(f"  [warn] {n}.toml 解析失败: {e}")
    return src




# 指南里不得出现的内容：某项目的专名与规模数据。
# 加新词时想清楚：这是「本机 Codex 配置的事实」还是「某个项目的产出」？
# 只有后者才禁。配置事实（模型档位、CLI 版本、委派次数）必须保留。
PROJECT_TERMS = [
    "ExcelInput", "ExcelTableParser", "ExcelAnalysisBuilder",
    "Code Ocean", "CodeOcean",
    "RxToolkits", "SeaWar", "RxCsharp", "projrx", "gyyx",
]
# 项目规模数据的特征形态（本机配置数据不含这些组合）
PROJECT_MEASURES = [
    r"\d+ 个生产文件", r"\d+ 个测试类", r"\d+ 个 partial",
    r"\d+ 条编号规则", r"\d+ 处规格引用",
]


def check_guide_purity(src: dict[str, str]) -> list[str]:
    """指南必须是「配置指南」，不是某项目的分析报告。"""
    problems: list[str] = []
    for scope in ("guide", "templates"):
        txt = src.get(scope)
        if not txt:
            continue
        for term in PROJECT_TERMS:
            for m in re.finditer(re.escape(term), txt):
                ln = txt[:m.start()].count("\n") + 1
                problems.append(f"{scope} L{ln}: 含项目专名 {term!r}")
        for pat in PROJECT_MEASURES:
            for m in re.finditer(pat, txt):
                ln = txt[:m.start()].count("\n") + 1
                problems.append(f"{scope} L{ln}: 含项目规模数据 {m.group(0)!r}")
    return problems



# 指南不得出现的实证/分析类表述。
# 判据：配置指南写「怎么配 + 为什么这么定」，不写「我们量到了什么」。
EMPIRICAL_TERMS = [
    r"实测",
    r"测量值",
    r"审查 \d+ 天会话",
    r"审查 \d+-\d+",
    r"条人类消息",
    r"含纠正信号",
    r"次 `unverified`",
    r"次 `failed`",
    r"次 `passed`",
    r"会话统计",
    r"日志分析显示",
    r"占比 \d+%",
    r"占 \d+%",
]
# 例外：这些行本身是在声明「不含」或是在描述产品机制
EMPIRICAL_ALLOW = [
    "不含",          # 范围声明里的否定式
    "(superseded)",  # 历史注记
]


def check_no_empirical(src: dict[str, str]) -> list[str]:
    """配置指南不得含实测数据与会话统计。"""
    problems: list[str] = []
    txt = src.get("guide")
    if not txt:
        return problems
    lines = txt.split("\n")
    for pat in EMPIRICAL_TERMS:
        for m in re.finditer(pat, txt):
            ln = txt[:m.start()].count("\n") + 1
            line = lines[ln - 1]
            if any(a in line for a in EMPIRICAL_ALLOW):
                continue
            problems.append(
                f"guide L{ln}: 含实证表述 {m.group(0)!r} —— "
                f"配置指南只写「怎么配 + 为什么这么定」")
    return problems


def check_guide_version(src: dict[str, str]) -> list[str]:
    """指南的版本日期不得早于本机 live 配置的最后修改日期。"""
    guide = src.get("guide", "")
    match = re.search(r"(?m)^\*\*版本\*\*：(\d{4}-\d{2}-\d{2})$", guide)
    if not match:
        return ["guide-version: 指南缺少 `**版本**：YYYY-MM-DD` 行"]
    try:
        version = datetime.date.fromisoformat(match.group(1))
    except ValueError:
        return [f"guide-version: 版本日期不是合法日期: {match.group(1)}"]
    paths = [GLOBAL_MD]
    paths += [os.path.join(AGENTS_DIR, name + ".toml") for name in AGENT_NAMES]
    paths += [os.path.join(CODEX, "config.toml")]
    modified = [datetime.date.fromtimestamp(os.path.getmtime(path))
                for path in paths if os.path.exists(path)]
    if not modified:
        return ["guide-version: 找不到 live 配置可比较（先安装并启动一次 Codex）"]
    latest = max(modified)
    if latest > version:
        return [f"guide-version: 指南版本 {version} 早于 live 配置最后修改 {latest}；运行 tools/sync-config.ps1"]
    return []


def check_toml_blocks(src: dict[str, str]) -> list[str]:
    """机械检查：**真正的配置块**里不得含未注释占位符。

    只检查可复制粘贴使用的配置块，不检查说明性 TOML。

    不检查的两类（否则会大量误报）：
      1. agent 文件正文——`developer_instructions` 里含报告格式模板，
         其中 `<file path>` 之类是给子代理填的，不是给人复制的配置。
      2. 指南里演示结构用的片段（如 §7.5 的错误信息示例）。

    判定标准：块内出现 `developer_instructions` / `description =` 即视为
    agent 正文，跳过。
    """
    problems = []
    for scope, txt in src.items():
        lines = txt.split("\n")
        i = 0
        while i < len(lines):
            m = re.match(r"^(`{3,})toml\s*$", lines[i].strip())
            if not m:
                i += 1
                continue
            n = len(m.group(1))
            body = []
            j = i + 1
            while j < len(lines):
                mm = re.match(r"^(`{3,})\s*$", lines[j].strip())
                if mm and len(mm.group(1)) >= n:
                    break
                body.append(lines[j])
                j += 1
            joined = "\n".join(body)
            # 跳过 agent 正文（含报告格式模板）
            if re.search(r"developer_instructions|^description\s*=", joined, re.M):
                i = j + 1
                continue
            # 跳过纯注释块（无活动行）
            active = [l for l in body if l.strip() and not l.strip().startswith("#")]
            if not active:
                i = j + 1
                continue
            for k, l in enumerate(body, 1):
                st = l.strip()
                if st.startswith("#") or not st:
                    continue
                if re.search(r"<[^>]+>|YourProject|path/to|your_", st):
                    problems.append(
                        f"{scope} toml 块 L{k} 未注释占位符: {st[:60]}")
            i = j + 1
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description="跨文件规则一致性检查")
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--only", help="只检查 key 含该子串的规则")
    args = ap.parse_args()

    src = load_sources()
    problems: list[str] = []

    print("=" * 88)
    print("check-consistency —— 全局规则 vs agent 文件 / 指南")
    print("=" * 88)
    print(f"  全局 AGENTS.md      {len(src['global']):>7,} 字符")
    for n in AGENT_NAMES:
        print(f"  agents/{n + '.toml':<18}{len(src['agent:' + n]):>7,} 字符")
    print(f"  配置指南            {len(src['guide']):>7,} 字符")
    print(f"  模板                {len(src['templates']):>7,} 字符")
    print()

    for rule in RULES:
        if args.only and args.only.lower() not in rule.key.lower():
            continue

        print(f"[{rule.key}] {rule.title}")
        if args.verbose and rule.why:
            print(f"    为什么: {rule.why}")

        # 1) 必需说法是否到位
        for scope in rule.applies_to:
            txt = src.get(scope, "")
            if not txt:
                problems.append(f"{rule.key}: {scope} 缺失或为空")
                print(f"    **{scope} 缺失**")
                continue
            required = rule.scoped_required.get(scope, rule.required)
            hits = [k for k in required if k.lower() in txt.lower()]
            if rule.require_all:
                missing = [k for k in required if k not in hits]
                ok = not missing
                detail = f"缺 {missing}" if missing else f"全中 ({len(hits)})"
            else:
                ok = bool(hits)
                detail = f"命中 {hits[0]!r}" if hits else f"期望其一 {rule.required}"
            if not ok:
                problems.append(f"{rule.key}: {scope} {detail}")
                print(f"    **{scope} {detail}**")
            elif args.verbose:
                print(f"    OK  {scope}  {detail}")

        # 2) 旧说法是否残留在「非守卫语境」
        for scope in ("global", "guide") + tuple(f"agent:{n}" for n in AGENT_NAMES):
            txt = src.get(scope, "")
            if not txt:
                continue
            for pat in rule.deprecate:
                hits = find_hits(txt, pat, rule.allow)
                if hits:
                    problems.append(f"{rule.key}: {scope} 残留旧说法 {hits[0]!r}")
                    print(f"    **{scope} 残留旧说法**: {hits[0]!r}")

        print(f"    -> {'有问题' if any(p.startswith(rule.key) for p in problems) else '一致'}")

    print()
    print(f"  规则数: {len(RULES)} 条表内规则"
          f"（另有 4 项附加检查：toml 占位符 / 指南纯度 / 实证表述 / 版本日期）")

    problems.extend(check_toml_blocks(src))
    problems.extend(check_guide_purity(src))
    problems.extend(check_no_empirical(src))
    problems.extend(check_guide_version(src))

    print()
    print("=" * 88)
    if problems:
        print(f"发现 {len(problems)} 项不一致:")
        for p in problems:
            print(f"  · {p}")
        print()
        print("修法：先改全局 AGENTS.md（源头），再同步 agents/*.toml 与指南。")
        print("      agents/*.toml 是实际发给子代理的那份——只改源头等于没改。")
    else:
        print("结论: 全部一致")
    print("=" * 88)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
