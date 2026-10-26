# Unity 发现与能力接入

## 只读发现

定位同时包含 Assets 与 ProjectSettings/ProjectVersion.txt 的目录。bootstrap 只看指定根及两层子目录；多个命中不自行选择，plan 报告后由操作者用 --unity-root 指定。有限探测不代表遍历全部源码，且不触发 Unity 导入。

读取 ProjectVersion.txt 确认实际 Editor 版本；读取已登记 Unity 根下的 Packages/manifest.json、packages-lock.json 识别包，按需检查图形/构建设置、现有 asmdef 及少量真实入口。仅凭包名不能证明当前场景/构建使用某个渲染管线或热更方案。

记录代码/资源/场景根、程序集依赖及平台宏、资源加载/释放、池/更新机制、日志入口、网络与存档边界、现有门禁。外部 Unity 安装和配置源路径由本人提供或本机配置解析，不猜盘符，不把绝对路径写入共享 profile。

## 能力登记合同

profile.capabilities 用稳定 ID 登记能力；字段和状态语义只在 [配置合同](../assets/project/Docs/ai/configuration.md) 维护。command 始终是可执行参数数组；人工菜单的真实文字与操作结果放 evidence，不当作可运行命令。只有实际核验工具且有修订及证据时记 verified；仅找到源码记 located；缺工具记 unconfigured。

unity.config_source、event_tools、ui_binding 只通过 capability 引用顶层能力，不另维护 state。旧字段在迁移时合并，避免两份状态冲突。checker 验证结构和引用，能力业务语义与命令运行分别验证。

| 能力 | 应核实的信息 | 验收 |
| --- | --- | --- |
| 编译/测试 | Editor 启动/CLI或现有 CI、测试程序集、结果日志 | 原始退出码和新增编译错误 |
| UI 绑定 | Prefab、手写逻辑、生成绑定、真实导出入口 | 控件一致、编译、交互及关闭后清理 |
| 资源/日志 | 项目已有加载释放/Logger接口、调用约定 | 引用、生命周期、设备表现 |
| 配表 | 源工程、格式、关联键、正式修改/验证/导出命令及产物 | 行级差异、关联ID、同批跨端一致 |
| 事件图 | 图格式、节点语义、编辑器保存/验证/导出及可自动化边界 | 结构和业务分支运行 |
| 专项审计 | GC/CPU、内存快照、Profiler 帧、Shader 构建日志、未使用类型的工具 | 按 [六类审计合同](../assets/project/Docs/ai/audit-capabilities.md) 提供证据，保留格式及动态根限制 |

策略对策划/美术的代码类型限制、TA 的 paths 与 code_paths 双重范围、内容归属和 Prefab 文件授权可执行静态检查；仍需阅读实际职责，不能凭后缀判定生成来源或聊天确认。迁移已有项目时保留其实体专门确认、程序集禁改、资源协作和 UI 人工复核制度，不用通用模板降低限制。

## 本机配置与外部工程

经本人明确提供，可将 Unity 安装、配置源根等个人信息写入被忽略的 `.ai-local/unity.json`。这是人工/agent 管理的本机记录，不由 checker 自动发现或认证；检查器的 identity 命令只管理另外的 `.ai-local.json`。

外部工程需要独立核对根目录、规则、身份、权限、已有改动和正式工具；本项目授权不自动覆盖外部路径。未获得路径或工具时仍可做导出侧只读定位及可解释预览，不声称源表已修改或已正式导出。

## 平台入口

环境根统一保存规则。若 Unity 根在子目录，bootstrap 同步创建该根的 AGENTS 和所选平台薄入口，引用上层权威规则；保留旧入口内容。不要在两个位置维护相同规则正文。需要独立维护多个 Unity 子项目时，先确定各自所有者和共同规则来源，分别预览冲突；不要让一个根的默认选择覆盖另一个。


## 测试、诊断与编辑器适配发现

先只读确认 Test Framework/Performance Testing 包及既有测试程序集、真实命令和结果格式，不添加 asmdef。确认分析器是否由实际构建加载并能导出带执行证据的 SARIF；IDE 提示单独记录。确认文本序列化、meta、UnityYAMLMerge 安装位置和已有 LFS 策略；只读资源检查按任务显式选路径。操作与输入合同见 [Unity 工具](../assets/project/Docs/ai/unity-tooling.md)。

需要编辑器桥接时先比较目标版本和实际功能：官方 CLI 当前 experimental，Pipeline 要求 Unity 6+；Coplay 按固定版本支持范围核对。仅选一个 unity-editor 组能力，先核工程身份、工具清单和只读查询。发现菜单/连接不等于项目专属导出/事件工具可用，原 capabilities 的能力证据仍须独立取得。


初始化扫描不限工程目录深度，完整记录所发现Unity根；多个根保持明确选择，不自动猜测。静态清单包括源码、asmdef/asmref、包清单、配置、文档、测试与资源元数据；Library等缓存、链接和敏感内容排除并留证。随后核读程序集/资源/配置/事件工具真实入口完成语义适配，不把目录名或包名推断成已验证能力。
