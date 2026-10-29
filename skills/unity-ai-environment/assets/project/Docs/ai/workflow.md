# 项目工作流选择与日常执行

<!-- ai-rule: workflow -->

当前模式由 [workflow.json](workflow.json) 唯一指定，工具状态仍在 [project-profile.json](project-profile.json)。本页是原生模式正文；初始化选择 `unity-harness-init` 时会换成 Harness 正文，并替换与其冲突的规则和模板，不同时执行两种流程。

## 初始化选择

初始化 `plan` 与 `apply` 的 JSON 结果都列出 `optional_tools`、`workflow_options` 和 `selected_workflow`。先向使用者展示每项名称、能力、前置和配置入口，再记录选择；未作选择时默认原生模式、外部工具关闭。用户可以选择暂不接入工具。

```text
python <skill-dir>/scripts/bootstrap.py plan --project <工作区根> --diff
python <skill-dir>/scripts/bootstrap.py plan --project <工作区根> --workflow native --tools unity-editor-cli --diff
python <skill-dir>/scripts/bootstrap.py apply --project <工作区根> --workflow native --tools unity-editor-cli
python tools/ai/project_setup.py list
python tools/ai/project_setup.py check
```

`--tools none` 表示不选可选工具。选择只写配置意向，不安装工具，不产生连接证据，也不将 capability 升级为 verified。官方 CLI、Coplay MCP、AnkleBreaker MCP 是三个提供者，沿用原 ID，不为工具名称再建重复能力。相同 `unity-editor` 组最多启用一个；已有工程使用自有桥接时登记其实际 provider。具体配方见 [Unity 工具](unity-tooling.md) 与 [工具信任边界](tool-integrations.md)。

已有环境省略 `--workflow` 时保留原模式。更换模式或已有受管定制时，`plan --diff` 展示冲突，`apply` 整批不写；维护者须合并差异、迁移状态源、停用旧宿主入口后验证，不通过删除文件或强制覆盖绕过。

## 定向上下文

初始化仍全面静态盘点；普通任务先按模块或目标文件找现有导航，不重新全扫。`context.py` 复用 context-index 与 Git 时效，不建立新索引，不读取源码正文：

```text
python tools/ai/context.py
python tools/ai/context.py --query <模块ID或别名> --query <另一模块>
python tools/ai/context.py --paths <仓库内文件或目录> ...
```

读取返回的必要规则、入口和直接依赖，按真实调用/注册/资源关联扩大范围；索引未命中时在已知父目录限定检索并补证据，不把“无匹配”当作全仓读取许可。`current` 只说明可观察范围没有漂移；`stale`/`unknown` 先复核。声明的门禁以 `not_run` 返回，必须另行运行。源码存在、序列化接线、真实执行各自取证。

## 完整职责切片与验证

继续使用 project-rules 的设计、任务与风险规则。需要拆分时，每个切片交付一个可观察结果，包含必要调用方、注册、资源接线和失败行为；不按规格章节或单个方法机械拆分。任务简报说明独占文件、只读共享接口、禁止修改范围和依赖。共享接口先定，注册/配置及同一场景资源由唯一写入者串行整合；不把 prompt 当文件锁。

逻辑变更适合自动化时先复现失败，再最小实现并做必要回归。纯逻辑优先既有 EditMode 程序集；生命周期、物理或场景交互使用合适的 PlayMode/真实场景证据。文案、机械修改和不可自动化的资源验收按风险选证据，不硬套上游“每个 public 方法一个测试”或固定新目录。高风险独立验证沿用原规则；此模式不强制 Copilot `/fleet`、第二模型系列或 Unity Skills REST。

## 按分支与执行者接力

任务状态只在 `Tasks/index.json`。在原任务正文记录当前分支/修订及 dirty 范围、执行者、相关导航 ID、决定与证据指针、已运行/未运行门禁，以及下一条可执行动作和验收命令。多执行者需要独立笔记时，使用 `Tasks/<task>-handoff-<branch-slug>-<actor-slug>.md` 并从原任务链接；它只存该执行者的上下文，不登记第二份任务状态，不覆写他人文件。

恢复时核对分支、源码/序列化/包/工具链/目标设备是否变化，重新验证受影响结论和下一动作；历史通过记录保留为历史，不能沿用为当前运行证据。只更新受影响导航、证据及自己的接力记录，不重写未受影响的文档。

## 可选的 Harness 模式

```text
python <skill-dir>/scripts/bootstrap.py plan --project <工作区根> --workflow unity-harness-init --diff
```

该模式保留上游的 Unity Skills REST 强制依赖、Copilot `/fleet`、TDD、不同模型系列独立评审、快照和维护窗口。选择会生成专属正文与前置清单；依赖缺失时停止相关执行，不回退为原生流程。安装或写入宿主配置仍须在使用者已选择并授权的范围内预览、应用与核验。初始化本身离线，不运行 npm、Editor 或外部服务。
