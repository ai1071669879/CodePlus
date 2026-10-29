#!/usr/bin/env python3
"""sync-guide.py —— 把 agent 配置同步进配置指南。

什么时候跑
----------
**每次改完 `agents/*.toml` 或 `~/.codex/AGENTS.md` 之后跑一次。**

它会做四件事：
  1. §3.1 内嵌的 `AGENTS.md` 全文  -> 与 `~/.codex/AGENTS.md` 逐字对齐
  2. §0 概览角色表 + §4.1 摘要表    -> 模型/档位/沙箱与 `agents/*.toml` 对齐
  3. `CODEX-AGENTS-TEMPLATES.md`    -> 用五个 agent 正文重新生成
  4. 头部版本日期                   -> 更新为今天

用法
----
    python -X utf8 sync-guide.py            # 只预览，不改文件（默认）
    python -X utf8 sync-guide.py --write    # 实际写入（先自动备份）

退出码：0 = 已同步或已修好；1 = 有需要人工处理的问题（缺 agent / 锚点 / 表头等缺结构时
        只报告、不写入，避免生成不完整内容）

设计要点
--------
* **用唯一文本锚点定位，不用行号。** 行号编辑在多次改动后会错位（实测踩过：
  一次 diff 错位把 verifier.toml 插到了 §3.2）。
* **默认 dry-run。** 写文件要显式 `--write`，并且先备份。
* **只改能机械确定的内容。** 叙述性文字（为什么这么定、踩过什么坑）不动。
* 与 `check-consistency.py` 分工：本脚本**同步**，那个**校验**。改完跑本脚本，
  再跑那个确认。
"""
from __future__ import annotations

import argparse
import datetime
import io
import os
import re
import shutil
import sys
import tomllib

HOME = os.path.expanduser("~")
CODEX = os.path.join(HOME, ".codex")
AGENTS_DIR = os.path.join(CODEX, "agents")
GLOBAL_MD = os.path.join(CODEX, "AGENTS.md")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GUIDE = os.path.join(REPO, "docs", "CODEX-SETUP.md")
TEMPLATES = os.path.join(REPO, "docs", "CODEX-AGENTS-TEMPLATES.md")

AGENT_ORDER = ("architect", "mech", "explorer", "verifier", "committer")

# §4.1 摘要表里每个 agent 的职责边界（文案，不是配置——改这里要人工判断）
DUTY = {
    "architect": "实现**已定设计**的切片；不做设计决策、不新增抽象与文件；缺信息则 `blocked`",
    "mech": "只做机械改动（重命名/格式化/模板/批量替换）；无设计判断",
    "explorer": "只读取证；不得创建/修改/删除任何文件；可上报观察到的风险（只报不修）",
    "verifier": "跑门禁、复现、证伪；**不得改源码**；只给裁决",
    "committer": "审 staged diff 与 `[Scope]` 一致性并机械分级；**不得改源码**；S0/S1 则中止提交",
}
# §0 概览表的「写入权限」列
WRITE = {
    "mech": "可写源码", "explorer": "只读",
    "verifier": "可写工作区，禁止改源码",
    "committer": "可写工作区（需写 `.git`），禁止改源码",
}
# §0 概览表的「定位」列：取 description 首句
def short_desc(desc: str, limit: int = 96) -> str:
    d = desc.strip()
    m = re.match(r"^([^.]{10,%d}\.)" % limit, d)
    return (m.group(1) if m else d[:limit]).strip()


def read(path: str) -> str:
    return io.open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n")


def load_agents(problems: list[str]) -> dict[str, dict]:
    out = {}
    for n in AGENT_ORDER:
        p = os.path.join(AGENTS_DIR, n + ".toml")
        if not os.path.exists(p):
            print(f"  [warn] 缺少 {n}.toml")
            problems.append(f"缺少 agents/{n}.toml（指南无法与该 agent 对齐）")
            continue
        try:
            out[n] = tomllib.loads(read(p))
        except (tomllib.TOMLDecodeError, OSError) as e:
            problems.append(f"agents/{n}.toml 无法读取或解析: {e}")
    return out


def replace_block(txt: str, start_marker: str, end_marker: str,
                  new_body: str, label: str, changes: list, problems: list) -> str:
    """把 start_marker 与 end_marker 之间的内容换成 new_body。

    先比较**去尾换行后**的内容，只有实质不同才改写——
    否则规范化本身（补/去尾换行）会让每次运行都误报改动。
    """
    i = txt.find(start_marker)
    if i < 0:
        changes.append(f"[跳过] {label}: 未找到起始锚点")
        problems.append(f"{label}: 未找到起始锚点")
        return txt
    s = i + len(start_marker)
    j = txt.find(end_marker, s)
    if j < 0:
        changes.append(f"[跳过] {label}: 未找到结束锚点")
        problems.append(f"{label}: 未找到结束锚点")
        return txt
    old = txt[s:j]
    if old.strip("\n") == new_body.strip("\n"):
        changes.append(f"[已一致] {label}")
        return txt
    new = "\n" + new_body.strip("\n") + "\n"
    changes.append(f"[同步] {label}  ({len(old):,} -> {len(new):,} 字符)")
    return txt[:s] + new + txt[j:]


def cell_replace(line: str, col: int, value: str) -> str:
    """替换 Markdown 表格行的第 col 列（**1 基**，与阅读表格的直觉一致）。

    注意：`| a | b |` 按 `|` 切分得到 ['', ' a ', ' b ', '']，
    所以第 col 列对应 parts[col]。
    """
    parts = line.split("|")
    if col >= len(parts) - 1:
        return line
    parts[col] = f" {value} "
    return "|".join(parts)


def cell_get(line: str, col: int) -> str:
    """取第 col 列（**1 基**）。"""
    parts = line.split("|")
    return parts[col].strip() if col < len(parts) - 1 else ""


def sync_table_columns(txt: str, header: str, key_col: int, key_fmt,
                       updates: dict[str, dict[int, str]],
                       label: str, changes: list, problems: list) -> str:
    """只同步表格的**配置列**，保留人工撰写的叙述列。

    updates: {行标识: {列号: 新值}}，行标识由 key_fmt(该行第 key_col 单元格) 得出。

    为什么只改列：§0/§4.1 的「定位/职责边界」列是**人工撰写的摘要**，
    用 description 自动截断会把它缩短（实测把
    "Mechanical execution agent: explicit, low-judgment edits only"
    截成 "Mechanical execution agent."，属于信息退化）。
    需要同步的只有模型、档位、沙箱这些**配置值**。
    """
    i = txt.find(header)
    if i < 0:
        changes.append(f"[跳过] {label}: 未找到表头")
        problems.append(f"{label}: 未找到表头")
        return txt
    lines = txt[i:].split("\n")
    k = 2
    while k < len(lines) and lines[k].startswith("|"):
        k += 1
    out = list(lines[:k])
    n_changed = 0
    seen = set()
    for r in range(2, k):
        key = key_fmt(cell_get(lines[r], key_col))
        if key not in updates:
            continue
        seen.add(key)
        new_line = lines[r]
        for col, val in updates[key].items():
            cur = cell_get(new_line, col)
            if cur != val:
                if os.environ.get("SYNC_DEBUG"):
                    print(f"      [debug] {key} 列{col}: {cur!r} -> {val!r}")
                new_line = cell_replace(new_line, col, val)
                n_changed += 1
        out[r] = new_line
    missing = set(updates) - seen
    if missing:
        changes.append(f"[注意] {label}: 表中缺 {sorted(missing)}")
        problems.append(f"{label}: 表中缺 {sorted(missing)}（该行的配置值无法同步）")
    if n_changed == 0:
        if not missing:
            changes.append(f"[已一致] {label}")
        return txt
    changes.append(f"[同步] {label}  ({n_changed} 个单元格)")
    old_block = "\n".join(lines[:k])
    new_block = "\n".join(out)
    return txt[:i] + new_block + txt[i + len(old_block):]


def main() -> int:
    ap = argparse.ArgumentParser(description="把 agent 配置同步进配置指南")
    ap.add_argument("--write", action="store_true", help="实际写入（默认只预览）")
    ap.add_argument("--no-templates", action="store_true", help="不重生成模板文件")
    args = ap.parse_args()

    for p in (GLOBAL_MD, GUIDE):
        if not os.path.exists(p):
            print(f"**缺少文件**: {p}")
            return 1

    problems: list[str] = []
    agents = load_agents(problems)
    log: list[str] = []
    agm = read(GLOBAL_MD).rstrip("\n")
    g = read(GUIDE)

    print("=" * 84)
    print("sync-guide" + ("" if args.write else "  【预览模式，未写入】"))
    print("=" * 84)
    print(f"  AGENTS.md   {len(agm):>8,} 字符")
    for n in AGENT_ORDER:
        if n in agents:
            a = agents[n]
            print(f"  {n:<12}{len(read(os.path.join(AGENTS_DIR, n + '.toml'))):>8,} 字符"
                  f"   {a.get('model')} @ {a.get('model_reasoning_effort')}")
    print()

    new_g = g

    # ---------- 1. §3.1 内嵌 AGENTS.md ----------
    new_g = replace_block(new_g, "````markdown\n", "\n````",
                          agm, "§3.1 内嵌 AGENTS.md", log, problems)

    # ---------- 2a. §0 概览角色表 ----------
    cfg_path = os.path.join(CODEX, "config.toml")
    if os.path.exists(cfg_path):
        cfg = read(cfg_path)
    else:
        cfg = ""
        problems.append("缺少 ~/.codex/config.toml（主线程模型/档位无法同步）")
    mm = re.search(r'(?m)^model = "([^"]+)"', cfg)
    me = re.search(r'(?m)^model_reasoning_effort = "([^"]+)"', cfg)
    upd0: dict[str, dict[int, str]] = {}
    if mm and me:
        upd0["主线程"] = {2: f"`{mm.group(1)}` @ `{me.group(1)}`"}
    for n in AGENT_ORDER:
        if n not in agents:
            continue
        a = agents[n]
        upd0[n] = {2: f"`{a.get('model')}` @ `{a.get('model_reasoning_effort')}`",
                   3: WRITE.get(n, "可写源码")}
    new_g = sync_table_columns(
        new_g, "| 角色 | 模型档位 | 写入权限 | 定位 |", 1,
        lambda c: c.strip("*` ").split("`")[0].strip(),
        upd0, "§0 概览角色表（模型/权限列）", log, problems)

    # ---------- 2b. §4.1 摘要表 ----------
    upd41: dict[str, dict[int, str]] = {}
    for n in AGENT_ORDER:
        if n not in agents:
            continue
        a = agents[n]
        upd41[n] = {2: f"`{a.get('model')}` @ `{a.get('model_reasoning_effort')}`",
                    3: f"`{a.get('sandbox_mode')}`"}
    new_g = sync_table_columns(
        new_g, "| 文件 | 模型 @ 档位 | 沙箱 | 职责边界", 1,
        lambda c: c.strip("` ").replace(".toml", ""),
        upd41, "§4.1 agent 摘要表（档位/沙箱列）", log, problems)

    # ---------- 3. 版本日期 ----------
    today = datetime.date.today().isoformat()
    m = re.search(r"(?m)^\*\*版本\*\*：(\d{4}-\d{2}-\d{2})$", new_g)
    if m:
        if m.group(1) != today:
            new_g = new_g[:m.start()] + f"**版本**：{today}" + new_g[m.end():]
            print(f"  [同步] 版本日期 {m.group(1)} -> {today}")
        else:
            print(f"  [已一致] 版本日期 {today}")

    # ---------- 4. §4.2 前补空行（Markdown 需要）----------
    if "偏好、\"下一步\"**禁止**（理由见 §7.21）。\n### 4.2 " in new_g:
        new_g = new_g.replace("（理由见 §7.21）。\n### 4.2 ", "（理由见 §7.21）。\n\n### 4.2 ")
        print("  [同步] §4.2 前补空行（原缺空行会导致渲染异常）")

    # ---------- 汇总 diff ----------
    print()
    print("=" * 84)
    print("同步日志")
    print("=" * 84)
    for l in log:
        print(f"  {l}")
    print()
    print("=" * 84)
    print("改动" + ("（将写入）" if args.write else "（预览）"))
    print("=" * 84)
    if new_g == g:
        print("  指南无需改动")
    else:
        print(f"  指南 {len(g):,} -> {len(new_g):,} 字符")

    # ---------- 模板文件 ----------
    tpl_new = None
    if not args.no_templates:
        tpl_old = read(TEMPLATES) if os.path.exists(TEMPLATES) else ""
        parts = []
        parts.append("# 子代理模板（五个 `agents/*.toml` 全文）\n")
        parts.append("本文件是 [`CODEX-SETUP.md`](./CODEX-SETUP.md) 的配套模板，"
                     "供**从零复原**时复制。")
        parts.append("目标路径：`<HOME>\\.codex\\agents\\`。\n")
        parts.append("仓库内的正式副本在 `codex/agents/`，由 `tools/sync-config.ps1` 从 live 快照生成；"
                     "重建机器时也可运行 `tools/install-codex-env.ps1 -Apply` 直接安装。\n")
        parts.append("五个文件的必需字段都是 `name`、`description`、`developer_instructions`。")
        parts.append("内容用**英文**（面向模型）。下面的 TOML 与可用配置**逐字一致**，"
                     "直接另存为同名文件即可。\n")
        parts.append("| 文件 | 模型 @ 档位 | 沙箱 | 一句话定位 |")
        parts.append("|---|---|---|---|")
        for n in AGENT_ORDER:
            if n not in agents:
                continue
            a = agents[n]
            parts.append(f"| `{n}.toml` | `{a.get('model')}` @ `{a.get('model_reasoning_effort')}` | "
                         f"`{a.get('sandbox_mode')}` | {short_desc(a.get('description',''), 40)} |")
        parts.append("\n> 五个文件都含同一段 **「上报观察，不给建议」** 条款："
                     "阻塞与带指向的观察必须上报，")
        parts.append("> 提案、方案排序、偏好、\"下一步\"禁止。理由见 `CODEX-SETUP.md` §7.21。\n")
        parts.append("---\n")
        for n in AGENT_ORDER:
            if n not in agents:
                continue
            body = read(os.path.join(AGENTS_DIR, n + ".toml")).rstrip("\n")
            parts.append(f"## `{n}.toml`\n")
            parts.append(f"{DUTY.get(n, '')}。\n")
            parts.append("````toml")
            parts.append(body)
            parts.append("````\n")
            parts.append("---\n")
        parts.append("## 复原方式\n")
        parts.append("```powershell")
        parts.append("# 把上面五个块分别另存到：")
        parts.append('$dir = "$env:USERPROFILE\\.codex\\agents"')
        parts.append("New-Item -ItemType Directory -Force $dir | Out-Null")
        parts.append("# architect.toml / mech.toml / explorer.toml / verifier.toml / committer.toml")
        parts.append("")
        parts.append("# 校验：五个文件都能解析，且必需字段齐备")
        parts.append('Get-ChildItem "$dir\\*.toml" | ForEach-Object {')
        parts.append("    $c = [System.IO.File]::ReadAllText($_.FullName, [System.Text.Encoding]::UTF8)")
        parts.append("    $n = if ($c -match 'name\\s*=\\s*\"([^\"]+)\"') { $Matches[1] } else { '缺失' }")
        parts.append("    $ok = ($c -match 'description') -and ($c -match 'developer_instructions')")
        parts.append('    "{0,-16} name={1,-12} 必需字段={2}" -f $_.Name, $n, $ok')
        parts.append("}")
        parts.append("```\n")
        parts.append("**重启 Codex** 后生效——`agents/*.toml` 在启动时读取。")
        tpl_new = "\n".join(parts) + "\n"
        if tpl_new == tpl_old:
            print("  [已一致] 模板文件")
        else:
            print(f"  [同步] 模板文件  ({len(tpl_old):,} -> {len(tpl_new):,} 字符)")

    # ---------- 写入 ----------
    # 有缺结构时不写：预览已展示，--write 也不能生成不完整内容。
    if problems:
        print("\n  存在需人工处理的问题：本次未写入任何文件。")
        print()
        print("=" * 84)
        print("需人工处理:")
        for p in problems:
            print(f"  · {p}")
        print("=" * 84)
        return 1
    if args.write:
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        if new_g != g:
            bak = f"{GUIDE}.bak-{stamp}"
            shutil.copy2(GUIDE, bak)
            io.open(GUIDE, "w", encoding="utf-8", newline="").write(new_g)
            print(f"\n  已写入指南；备份 {os.path.basename(bak)}")
        if tpl_new is not None and tpl_new != (read(TEMPLATES) if os.path.exists(TEMPLATES) else ""):
            if os.path.exists(TEMPLATES):
                bak = f"{TEMPLATES}.bak-{stamp}"
                shutil.copy2(TEMPLATES, bak)
            io.open(TEMPLATES, "w", encoding="utf-8", newline="").write(tpl_new)
            print(f"  已写入模板")
    else:
        if new_g != g or tpl_new is not None:
            print("\n  加 --write 才会落盘。")

    print()
    print("=" * 84)
    print("完成。改完建议再跑一次 check-consistency.py 做校验。")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
