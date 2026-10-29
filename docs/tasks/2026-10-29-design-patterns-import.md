# design-patterns 本机技能入库

请求：将本机 design-patterns skill 加入仓库。

## 意图与结构

本记录对以下路径的范围说明优先于通用最小改动规则；不改变权限、提交或验证要求。

- [Keep] 本机 `~/.codex/skills/design-patterns/` 七个文件原文保持权威；已有两个环境技能及全局配置保持现状。继续使用已有镜像、安装、备份和哈希机制。
- [Rewrite] `tools/sync-skills.ps1`、`tools/install-skills.ps1`、`tools/verify-repo.ps1` 的默认技能名单和相关说明；根 README、项目 AGENTS、skills/README 与 tools/README 的技能索引。
- [Forbidden] 不修改导入技能正文，不新增同步器，不写 live 配置，不提交或推送。禁止内容改动由七文件 SHA-256 一致性检查判定。
- [Superseded] 上述索引/脚本把仓库技能限定为两个环境生成器的表述，自本任务起失效；两个环境生成器本身的职责不变。

Shape First：核心概念为技能快照、默认管理名单、仓库导航。复用 `tools/sync-skills.ps1 -Only design-patterns`、两个安装/同步脚本的 `$Only` 参数及 `verify-repo.ps1` 已有 `Get-TreeHash`，不引入新抽象。可读实现是在 `skills/design-patterns/` 保存完整七文件目录，现有三脚本各追加一个默认 ID，索引描述新增技能的独立用途。

| 操作 | 路径 | 复用依据 |
| --- | --- | --- |
| 导入原文 | skills/design-patterns/ | 本机已有完整技能，通过现有 sync-skills 镜像 |
| 扩充默认名单 | tools/sync-skills.ps1、tools/install-skills.ps1、tools/verify-repo.ps1 | 已有参数、预览、备份、哈希比较足够 |
| 更新导航 | README.md、AGENTS.md、skills/README.md、tools/README.md | 现有索引直接追加，不另建指南 |

## 验证

本任务仅本地文件操作，不使用网络、不上传数据。风险为 Medium：三个脚本仅默认名单改变，同步预览、安装预览、逐文件哈希和既有仓库门禁覆盖。

- 导入：`powershell -NoProfile -ExecutionPolicy Bypass -File tools/sync-skills.ps1 -Only design-patterns`，exit 0，`mirrored (7 files)`。
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools/sync-skills.ps1 -Preview`：exit 0，三个技能均 `same`，包括 design-patterns。
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools/install-skills.ps1`：exit 0，`需要安装：0 项；相同跳过：3 项；源缺失：0 项`，未写 live。
- `python -B -X utf8 C:/Users/Administrator/.codex/skills/.system/skill-creator/scripts/quick_validate.py D:/ProjRx/CodePlus/skills/design-patterns`：exit 0，`Skill is valid!`。
- 主线程标准库检查（`@' ... '@ | python -B -X utf8 -`）：exit 0，`SHA256: 7/7 files identical to live`、`RELATIVE LINKS: 18 checked, 0 broken`。这是原文镜像验证，不宣称真实设计任务的行为评估。
- `powershell -NoProfile -ExecutionPolicy Bypass -File tools/verify-repo.ps1`：exit 0，八组 PASS，包括 `skills/design-patterns`；`全部通过：本机 live 环境与仓库快照一致（全局环境 + 项目技能）。`
- `python -B -X utf8 tools/check-consistency.py`：exit 0，19 条规则及附加检查一致，`结论: 全部一致`。
- `git -c safe.directory=D:/ProjRx/CodePlus diff --check`：exit 0，无空白错误；仅报告既有换行转换提示。

执行代理回报（主线程已核对：三个可执行脚本均在 tools 一个源码模块，其余为索引文档；不触发跨两模块独立验证条件）：

```text
status: passed
changed_files:
  - tools/sync-skills.ps1
  - tools/install-skills.ps1
  - tools/verify-repo.ps1
  - README.md
  - AGENTS.md
  - skills/README.md
  - tools/README.md
reused:
  - sync/install 的既有 -Only 名单、verify 的既有哈希循环、既有仓库索引
evidence:
  - command: python -B -X utf8 tools/check-links.py
    exit_code: 0
    key_output: checked 28 relative links in 10 documents
  - command: PowerShell here-string 管道输入 Python 标准库检查
    exit_code: 0
    key_output: 三个脚本均保留 UTF-8 BOM，各有唯一三技能名单
assumptions:
  - 代理回报时主线程门禁尚未运行；已由上方实际输出解决，无遗留未验证项
blockers:
  - none
```

最终接受：七文件原文导入，默认名单与导航更新；未修改 live 或导入正文，未修改已有环境技能，未提交/推送。所有本任务门禁已完成。
