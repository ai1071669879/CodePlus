# Unity 工具与分层验收

<!-- ai-rule: unity-tooling -->

本页定义 U2–U4 的测试/性能、诊断和资源检查，以及按需 U1 编辑器适配。共用 [工具信任规则](tool-integrations.md) 与 [能力字段合同](configuration.md)。先从目标工程 ProjectVersion.txt、Packages 清单/锁文件和实际工具帮助确认版本；本包不固定 Unity/渲染管线，不安装依赖、不启动 Editor 或重写工程设置。

## U2：测试与性能预算

在既有测试程序集内复用 Unity Test Framework；不自动新增或修改 asmdef/引用。根据已安装包版本核对命令行帮助。下列模板在工作区根执行，实际 Unity 可执行文件和工程根从本机配置解析；项目有自己的测试入口时优先用它：

```text
<Unity-executable> -runTests -batchmode -projectPath <Unity-root> -testResults <结果XML路径> -testPlatform EditMode
<Unity-executable> -runTests -batchmode -projectPath <Unity-root> -testResults <结果XML路径> -testPlatform PlayMode
python tools/ai/unity_checks.py tests --report <相对NUnit报告.xml> --exit-code <实际Unity进程退出码>
```

不要盲加 -quit 提前结束测试；GPU/渲染测试不要盲加 -nographics。Editor 正占用、授权和目标平台依赖都需按工程环境处理。保存命令、版本、代码修订、目标平台与退出码。解析器支持 NUnit2/3 叶子测试结果，拒绝损坏/含实体声明的 XML、未知状态、失败/根失败、零执行及全跳过；只读 UTF-8（可含 BOM）。未提供真实进程退出码时 process_exit_verified=false，不能推断进程成功。XML 通过不证明测试覆盖充分、来源真实或 Player 通过。

Performance Testing 必须使用项目兼容版本，先确认测试程序集已经引用 Unity.PerformanceTesting；需要改程序集边界时按原项目制度处理。热身次数、采样次数、聚合统计（例如中位数）按具体指标设计并留证；Measure.Method 的 .GC() 统计分配调用次数，不能当字节数。Editor 与 Development Player 有额外开销，结论不能直接当发布包/目标设备表现。

预算唯一文件是 [unity-validation.json](unity-validation.json)：schema_version=1，performance={context,metrics}。context 是需一致的运行环境子集；metrics 每条含 name、unit、min_samples（正整数），至少一个 max/min/max_regression_pct 约束。初始空 metrics 返回 2（未配置），不编造通用帧率或内存预算。max_regression_pct 是非负百分比，只适用于越小越好的指标；反向指标用 min。所有数值必须有限且不能是 bool。

归一化样本合同：schema_version=1、source_revision、context、metrics。context 必含非空 editor_version/platform/device/scenario/backend/build_mode；每个 metric 含唯一 name、unit、有限 value、正整数 sample_count。value 是已选择统计方法得到的聚合值，原始测量与统计方法另留证。预算项必须全有，单位和最少样本数要匹配。相对回归还须提供 baseline，其完整 context 必须一致、对应值大于零，不拿跨设备/构建模式数据硬比。

```text
python tools/ai/unity_checks.py performance --samples <相对样本.json> --expected-revision <实际修订>
python tools/ai/unity_checks.py performance --samples <相对样本.json> --baseline <同环境基线.json> --expected-revision <实际修订>
```

本入口检查归一化数据与预算，不解析 .snap/Profiler 原生数据，不证明测量方法正确。已有性能审计继续按 [audit-capabilities.md](audit-capabilities.md) 定向取证。

## U3：Microsoft.Unity.Analyzers

先确认目标 Editor、IDE、编译器和分析器兼容版本，再按项目既有依赖制度接入。IDE 出现提示不证明 CI/命令行构建启用了分析器。保留受保护的严重级别策略，缺少规则不能靠清空报告冒充通过；不要为消警随意降低 error/warning 或加全局抑制。

```text
python tools/ai/unity_checks.py diagnostics --report <相对SARIF.json> --require-tool Microsoft.Unity.Analyzers --level error
```

输入为真实编译/分析工具导出的 SARIF 2.1.0；runs 非空、driver 或 extensions 明确标记所需工具，每个 run 的 invocations 具有 executionSuccessful=true。没有工具/执行证明返回 2，执行失败/命中门禁返回 1。`--level warning` 把 warning 也作为失败。编译器不输出上述字段时保留原件，由可信适配器附带实际分析器加载和退出码证据，不能手填成功假装原生支持。空结果须同时有执行证据才可通过；仍不证明所有 Unity 生命周期/资源问题已覆盖。

## U4：资源、合并与大文件

本包提供只读 Assets `.meta`/GUID 检查，按 profile.unity.root 解析工程根。默认不全扫，显式选择范围：

```text
python tools/ai/unity_checks.py assets --paths <相对Assets内目录或文件> ...
python tools/ai/unity_checks.py assets --all-assets
```

检查选中目录/文件与 meta 配套、孤儿 meta、唯一且合法的32位十六进制 guid、范围内重复 GUID。Assets 根本身不要求 meta；选中子目录本身要求 meta。不走 Library、Packages 或隐藏目录，不允许链接逃逸。重复检查只覆盖本次选中范围；该命令没有扫描全项目引用，不得写“所有引用完整”。不自动修 GUID、资源或序列化内容。

需合并场景/Prefab 时，先确认工程已经采用适合的文本序列化设置及可见 meta；改变设置可能触发大批资源变化，须单独预览和协调。使用对应 Editor 安装的 UnityYAMLMerge；先查看该版本帮助，以官方 Smart Merge 配置为依据，把解析出的程序路径写本机 Git 配置。先在临时副本对已知冲突样本运行并复核资源引用，再用于真实合并；无法自动解决的冲突交由资源负责人在 Editor 核验，不手工猜 GUID。

以下是供维护者合并到本机仓库 Git config 的配置模板（不是 PowerShell 命令，不写全局配置）；替换本机工具路径后核对实际 diff，再用 `git mergetool --tool=unityyamlmerge -- <冲突资源相对路径>`。共享文档保留占位符，变量由 Git 的 mergetool 进程提供：

```ini
[merge]
    tool = unityyamlmerge
[mergetool "unityyamlmerge"]
    trustExitCode = false
    cmd = '<UnityYAMLMerge本机路径>' merge -p "$BASE" "$REMOTE" "$LOCAL" "$MERGED"
```

Git LFS 仅按团队已有大文件策略选择二进制后缀并预览 .gitattributes 变化；不要把 .unity/.prefab/.meta 一概转 LFS，避免丢失文本合并能力。已确认要追踪新 PSD 文件时，可在项目根执行 `git lfs track "*.psd"`，核对并随变更提交 .gitattributes；既有大文件的迁移另立任务。服务端支持、配额、锁定和 CI 拉取要单独实测。本 skill 不迁移历史、不重写提交；LFS 也不替代多人资源编辑归属协调。

## U1：使用者选择的 Editor 工具

初始化的 `optional_tools` 列出全部工具与配置入口，`--tools` 按能力 ID 选择。工具选择只登记意向，不安装或连接；默认可全部跳过。`unity-editor-cli` 对应官方 CLI，`unity-editor-mcp` 对应 Coplay，`unity-editor-anklebreaker` 对应 AnkleBreaker，不按产品名再建重复 ID。

三者与 `unity-skills-rest` 同属 `unity-editor` 互斥组，最多一个 enabled。选中 Harness 模式时 REST 为强制主通道；其它桥接不能替代。版本/工具数随上游变化，不将网页数字写成固定承诺。实际能力以固定版本、目标工程已装包和现场工具清单为准。

<a id="unity-cli"></a>

### Unity 官方 CLI — unity-editor-cli

能力：管理工程/Editor/构建环境；配合 Pipeline 在已打开 Editor 中操作场景、资源、脚本与测试，支持项目自定义命令和官方 MCP 模式。Pipeline 的兼容版本、权限和连接状态按目标工程核对。

1. 先读取 [官方安装说明](https://docs.unity.com/en-us/unity-cli/use-unity-cli) 与所选版本 help，固定 CLI 发布版及 Pipeline 包版本。确认 UPM/ProjectSettings 改动、安装范围和网络边界后安装，不让初始化器下载执行远程脚本。
2. Windows 可先查看 `winget show --id Unity.CLI --versions`，按已选版本安装；其他平台按官方固定发布物。运行 `unity --version`、`unity --help` 核验实际入口，本机路径放 `.ai-local/tools.json` 的 `unity-editor-cli` 映射。
3. Editor 交互需要 Pipeline。先核 `unity pipeline install --help` 并预览目标包变化，再在已授权工程按固定版本提供的方式接入；只读管理 CLI 能用不表示 Pipeline 已接好。
4. 在正确工程运行 `unity status`，核工程路径、Editor 版本、PID/端口；通过 `unity list` / `unity command` 发现该版本命令 schema，再选最小只读查询。编译、测试和实际修改另留命令与结果，不拿 status 当功能验收。
5. profile 中填写 command、integration.version/license/probe 及证据；默认 probe 为 `["unity","--version"]`。需要 MCP 模式时先核 `unity mcp --help`，审阅其配置候选，只合并所选客户端条目，保留其它服务/入口；不自动运行配置全体客户端的命令。

<a id="coplay"></a>

### CoplayDev unity-mcp — unity-editor-mcp

能力：场景/GameObject、脚本、资产、测试、性能与构建，按实际版本选择工具组；适合日常 Editor 工作。专业子系统仍以现场工具与工程依赖为准。

1. 核对 [官方 README](https://github.com/CoplayDev/unity-mcp) 的 Editor、Python/uv 要求；固定服务端和 Editor 包的兼容 tag/commit，记录 MIT 等实际发布版许可。
2. 先预览 Unity Package Manager 依赖变化，获授权后从 `https://github.com/CoplayDev/unity-mcp.git?path=/MCPForUnity#<已核验tag或commit>` 接入。路径与 fragment 是版本模板，不执行含占位符的命令。
3. 打开该版本 MCP for Unity 面板，核工程、服务状态、传输和端口。按该版本生成的配置手工合并所选客户端：HTTP 只填实际本地 `/mcp` endpoint，stdio 只填经审阅的固定服务启动 argv；保留无关 MCP 服务，不默认 Configure All Detected Clients。
4. 用 MCP Inspector 核 tools/list 和所选工具 schema，确认连接工程；只启用当前任务需要的组，先做只读场景/控制台查询，再按任务授权用写工具。
5. 在 capability 登记真实 transport、endpoint 或 command、version、环境变量名、核验修订与证据。doctor 的 executable/probe 结果不等于 MCP 握手成功；版本、连接、读操作、写入各自留证。

<a id="anklebreaker"></a>

### AnkleBreaker unity-mcp-server — unity-editor-anklebreaker

能力：场景、组件、资源、构建和性能；专业能力扩展至 Shader Graph、Amplify、地形、物理、NavMesh、动画等。多工程路由、每 Editor 队列、MPPM/ParrelSync 和高级 schema 按需发现，需要对应包及版本支持。

1. 核 [server](https://github.com/AnkleBreaker-Studio/unity-mcp-server)、[Unity plugin](https://github.com/AnkleBreaker-Studio/unity-mcp-plugin) 与 [配置说明](https://github.com/AnkleBreaker-Studio/unity-mcp-server/blob/main/docs/configuration.md)。server/plugin 独立固定 tag/commit 并核兼容；核 Node.js 需求。研究时 server LICENSE 为 AnkleBreaker Open License v1.0，部署仍以固定发布物条款为准。
2. 先预览 UPM 变化，再按授权将 `https://github.com/AnkleBreaker-Studio/unity-mcp-plugin.git#<固定tag或commit>` 接入。server 使用已审阅的固定 checkout 和锁文件安装依赖，不从浮动 main/latest 自动执行。
3. 在当前版 AB Unity MCP Dashboard 核桥接状态。客户端 stdio 条目模板为 `{"command":"node","args":["<本机固定server目录>/src/index.js"]}`；只合并该条目。登记 `UNITY_BRIDGE_HOST/PORT` 等所需环境变量名，实际本机值与路径不放共享配置。command 至少包含真实 server 入口，单独 `node` 不能证明服务可用。
4. tools/list 后调用 `unity_list_instances`，按实际工程名/路径选择 `unity_select_instance`。多工程/多代理在后续调用携带发现的 port 和稳定 agentId；Editor 重启重新发现，不使用示例固定端口。
5. 先用 `unity_editor_state` 等已核 schema 的只读工具验证工程身份。专业能力先 `unity_list_advanced_tools` 搜索分类、读取单项 schema，再调用 `unity_advanced_tool`；未装可选包时保留缺项，不为开启功能擅自装包。
6. 填 capability command 为 `["node","<已选择的固定入口>"]`（个人路径用本机设施，团队路径使用真实相对入口），transport=stdio、版本/许可/证据；server 与 plugin 版本分别留证。doctor 版本探测不会认证 Editor 连接。超时或结果未知时先查原任务/工程再决定是否重发写入，不把超时当撤销。

统一收口：配置只选一个主通道，执行 `project_setup.py list/check` 与 `environment.py doctor`，再按上面步骤完成实际连接和最小功能测试。只有真实证据齐全才能更新 verified。通用桥接不自动提供本项目的配表、事件图、导出器和业务菜单，它们仍在 capabilities 单独登记。

## U0：编辑器内中继（可选，默认不启动 Editor）

工程已在 Editor 中打开、又需要稳定的自动化通道（刷新导入、调用受权 Editor 方法、留证）时，可启用随包中继。它不替代 U1 的官方 CLI/MCP；不装依赖、不改工程设置、不自动启动 Editor。

| 文件 | 作用 |
| --- | --- |
| `Editor/UnityEditorGate/UnityEditorGate.cs` | `[InitializeOnLoad]` 轮询请求；只执行 `refresh`/`wait-compile`/`invoke`；写 JSON 回执；域重载后把上次未完成请求标记失败 |
| `tools/ai/unity_editor.py` | `discover/status/request/wait/run/tests/player/log`；`tests` 仍调用 `unity_checks.py tests` 做 NUnit 判定 |

```text
python tools/ai/unity_editor.py discover
python tools/ai/unity_editor.py run --id refresh-01 --suite refresh
python tools/ai/unity_editor.py run --id capture-01 --suite invoke --type MyProject.EditorTools.SceneCapture --method Capture --arg map-01
python tools/ai/unity_editor.py tests --platform editmode
python tools/ai/unity_editor.py log "$env:LOCALAPPDATA/Unity/Editor/Editor.log" --require-clean
```

- gate 根目录为 `<UnityRoot>/Temp/UnityEditorGate/<pid>/`；`request.json` 被认领后移入 `<id>/`，`<id>/result.json` 是终态，`rejected-*.json` 记录拒绝原因。协议与失败模式见技能的 `references/unity-editor-automation.md`（安装后也可从 `tools/ai/unity_editor.py --help` 读取命令面）。项目专属 suite、截图/采集与构建通过 `invoke` 调用工程自己的静态方法，本包不内置这些业务逻辑。
- 只按 `Library/EditorInstance.json` 的 PID 定位，不猜实例、不自动杀 Editor；同 id 永不覆盖。建议在 `<gate根>/allowlist.json` 声明 `{"methods":["Namespace.Type.Method"]}` 收窄 `invoke`，并在任务记录中写明授权范围。
- 回执只证明请求被认领/返回；`refresh` 不声称编译成功，`tests` 以真实进程退出码与 NUnit 报告为准，Player 超时不算通过。退出码：`0` 成功；`1` 运行失败/超时/测试失败；`2` 用法或前置条件不满足。
- 不需要该通道时删除 `Editor/UnityEditorGate/`；它不参与 check 的必需文件集合，也不影响其他检查器。

## 来源与许可

核对日期：2026-10-17，安装时复核选定发布物。

- [Unity Test Framework CLI](https://docs.unity3d.com/Packages/com.unity.test-framework@1.4/manual/reference-command-line.html)；[Performance Testing](https://docs.unity3d.com/Packages/com.unity.test-framework.performance@3.2/manual/index.html) 和 [Measure.Method](https://docs.unity3d.com/Packages/com.unity.test-framework.performance@3.2/manual/measure-method.html)。文档版本是依据示例，目标工程选择兼容包；Unity 包/Editor 条款由其固定发布版提供。
- [Microsoft.Unity.Analyzers](https://github.com/microsoft/Microsoft.Unity.Analyzers)：MIT；本包不复制其诊断实现。
- [Unity Smart Merge](https://docs.unity3d.com/6000.0/Documentation/Manual/SmartMerge.html)、[Git LFS](https://git-lfs.com/) 与 [LFS 配置步骤](https://docs.github.com/en/repositories/working-with-files/managing-large-files/configuring-git-large-file-storage)：使用正式工具和项目既有策略。
- [Unity CLI](https://docs.unity.com/en-us/unity-cli/unity-cli-reference) 与 [Pipeline 要求](https://docs.unity.com/en-us/unity-cli/unity-pipeline/unity-pipeline-package)；[Coplay Unity MCP](https://github.com/CoplayDev/unity-mcp)（MIT）。不把实验性接口承诺为稳定/全版本通用能力。
