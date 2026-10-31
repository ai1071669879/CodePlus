#!/usr/bin/env python3
"""check-consistency.py —— live 规则层与指南/模板的一致性检查。

用途
----
规则只保留「不可读、不可验」的少数几条；其余约束由仓库里的脚本与文件承担
（写域互斥、门禁、报告字段、brief 形状）。本脚本只检查两件事：

1. 少量不变量在 live 与指南中一致：三条不变量 / 停而非猜 / 设计归属 /
   机器事实 / 委派指针。
2. 规则层体积不回升：行数预算（AGENTS.md、DELEGATION.md、agents/*.toml）。

另有 6 项附加检查（体积预算 / 层边界 / toml 占位符 / 指南纯度 / 实证表述 / 版本日期），见 main()。

退出码：0 = 一致；1 = 发现不一致
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
        key="invariants",
        title="三条不变量（交付=门禁 / 单写者 / 事实在文件）",
        required=["gate command exits 0", "one writer per path", "truth is in files"],
        applies_to=("global", "guide"),
        require_all=True,
        deprecate=[r"the report is the record", r"delivery is the brief"],
        allow=["(superseded)", "已废弃"],
        why="交付定义、写域互斥、事实来源是全局唯一的硬不变量；两处文本必须一致。",
    ),
    Rule(
        key="stop-not-guess",
        title="停而非猜",
        required=["stop instead of guessing"],
        applies_to=("global", "guide"),
        require_all=True,
        deprecate=[r"make a reasonable assumption", r"best guess"],
        allow=["(superseded)", "已废弃"],
        why="子代理缺上下文时编造，是返工的主要来源。",
    ),
    Rule(
        key="decision-ownership",
        title="执行方不做设计决定",
        required=["do not make design decisions"],
        applies_to=("agent:architect", "agent:mech", "agent:explorer",
                    "agent:verifier", "agent:committer"),
        require_all=True,
        deprecate=[r"you own the design", r"decide the structure"],
        allow=["(superseded)", "已废弃"],
        why="五个子代理各自读自己的 toml；谁都不许替主线程做设计决定。",
    ),
    Rule(
        key="machine-facts",
        title="沙箱档位与网络默认（事实）",
        required=["danger-full-access", "command network access"],
        applies_to=("global", "guide"),
        require_all=True,
        deprecate=[r"only two sandbox modes", r"has only two modes", r"只有两种模式"],
        allow=["(superseded)", "已废弃", "已作废"],
        why="三种模式、网络默认关闭是事实；写错会误导风险判断。",
    ),
    Rule(
        key="delegation-pointer",
        title="委派剧本单独成文，主线程按需读",
        required=["DELEGATION.md"],
        applies_to=("global", "guide"),
        require_all=True,
        deprecate=[],
        allow=[],
        why="委派细则不再注入每个线程；指针必须在，正文在 DELEGATION.md。",
    ),
    Rule(
        key="guide-sync-entry",
        title="指南指向同步入口",
        required=["sync-config.ps1"],
        applies_to=("guide",),
        require_all=True,
        deprecate=[],
        allow=[],
        why="改 live 后必须同步快照；指南要指向那条命令。",
    ),
]


def read_text(path: str) -> str:
    if not os.path.exists(path):
        return ""
    return io.open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def load_sources() -> dict[str, str]:
    src = {"global": read_text(GLOBAL_MD),
           "delegation": read_text(os.path.join(CODEX, "DELEGATION.md")),
           "guide": read_text(GUIDE), "templates": read_text(TEMPLATES)}
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
# 全局环境正文不得出现项目技能模块的名称与配置键（仓库 AGENTS.md「严格分离」第一条）。
MODULE_TERMS = [
    "project-ai-environment", "unity-ai-environment", "[[skills.config]]",
]


def check_guide_purity(src: dict[str, str]) -> list[str]:
    """指南必须是「配置指南」，不是某项目的分析报告，也不得混入项目技能模块内容。"""
    problems: list[str] = []
    for scope in ("guide", "templates"):
        txt = src.get(scope)
        if not txt:
            continue
        for term in PROJECT_TERMS:
            for m in re.finditer(re.escape(term), txt, re.I):
                ln = txt[:m.start()].count("\n") + 1
                line = txt.split("\n")[ln - 1]
                # 本仓库自身的绝对路径含 ProjRx，不是项目专名泄漏。
                if "CodePlus" in line:
                    continue
                problems.append(f"{scope} L{ln}: 含项目专名 {term!r}")
        for pat in PROJECT_MEASURES:
            for m in re.finditer(pat, txt):
                ln = txt[:m.start()].count("\n") + 1
                problems.append(f"{scope} L{ln}: 含项目规模数据 {m.group(0)!r}")
        for term in MODULE_TERMS:
            for m in re.finditer(re.escape(term), txt):
                ln = txt[:m.start()].count("\n") + 1
                problems.append(f"{scope} L{ln}: 含项目技能模块内容 {term!r}")
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


# ---- 规则层体积预算：让精简不可逆 -------------------------------------------
# 规则总量只许持平或下降：要加一条，先删等量文本。超限时这里直接失败。
BUDGET_LINES = {
    "AGENTS.md": 80,          # 注入每线程的全局规则
    "DELEGATION.md": 90,      # 主线程按需读的委派剧本
    "agents/*.toml": 70,      # 每个子代理一读
}


def _count_lines(path: str) -> int:
    return len(io.open(path, encoding="utf-8").read().splitlines())


def check_rule_budget() -> list[str]:
    """规则层行数预算，防止精简后重新长回去。"""
    problems: list[str] = []
    targets = [
        ("AGENTS.md", GLOBAL_MD, BUDGET_LINES["AGENTS.md"]),
        ("DELEGATION.md", os.path.join(CODEX, "DELEGATION.md"), BUDGET_LINES["DELEGATION.md"]),
    ]
    for name in AGENT_NAMES:
        targets.append((f"agents/{name}.toml", os.path.join(AGENTS_DIR, name + ".toml"),
                        BUDGET_LINES["agents/*.toml"]))
    for label, path, cap in targets:
        if not os.path.exists(path):
            problems.append(f"budget: {label} 缺失（规则层不完整）")
            continue
        got = _count_lines(path)
        if got > cap:
            problems.append(f"budget: {label} {got} 行 > 上限 {cap} 行 —— 先删再加")
    return problems


# ---- 层边界：全局层不得引用项目布局、外部仓库名或绝对路径 ----
# 边界规则（写进文档靠自觉，写进这里靠 exit 1）：
#   Codex 全局层只描述 Codex 自身；项目具体布局由项目自己的 AGENTS.md 声明。
BOUNDARY_PATTERNS = [
    r"CodePlus", r"ProjRx", r"RxToolkits",           # 外部仓库/项目名
    r"[A-Za-z]:\\",                                # 盘符绝对路径
    r"\bTasks/", r"docs/ai", r"tools/ai",           # 项目侧布局
    r"slice\.py", r"slices\.json", r"briefs/",     # 项目侧工具与状态文件
]


def check_layer_boundary() -> list[str]:
    """全局层出现项目侧内容即越界：子代理会在无关项目里照着不存在的路径干活。"""
    problems: list[str] = []
    targets = [("AGENTS.md", GLOBAL_MD),
               ("DELEGATION.md", os.path.join(CODEX, "DELEGATION.md"))]
    targets += [(f"agents/{n}.toml", os.path.join(AGENTS_DIR, n + ".toml")) for n in AGENT_NAMES]
    for label, path in targets:
        if not os.path.exists(path):
            continue
        text = io.open(path, encoding="utf-8").read()
        for pat in BOUNDARY_PATTERNS:
            for m in re.finditer(pat, text):
                ln = text[:m.start()].count("\n") + 1
                problems.append(
                    f"boundary: {label} L{ln} 越界引用 {m.group(0)!r} —— 项目侧内容放项目 AGENTS.md")
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
    print(f"  DELEGATION.md       {len(src.get('delegation', '')):>7,} 字符")
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
          f"（另有 6 项附加检查：体积预算 / 层边界 / toml 占位符 / 指南纯度 / 实证表述 / 版本日期）")

    problems.extend(check_rule_budget())
    problems.extend(check_layer_boundary())
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
        print("修法：先改 live（~/.codex/AGENTS.md、DELEGATION.md、agents/*.toml），")
        print("      再跑 tools/sync-config.ps1 同步指南与快照。")
        print("      体积超限时先删，再加——规则总量只许持平或下降。")
    else:
        print("结论: 全部一致")
    print("=" * 88)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
