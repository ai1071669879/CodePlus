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

## U1：按需选择一个编辑器适配

| 能力 ID | 适用与接入 | 限制 |
| --- | --- | --- |
| unity-editor-cli | Unity 官方 CLI，当前为 experimental；按官方发布固定版本，检查 status/project/help，确认连接的 Editor 和工程路径，再用只读场景/测试清单验证 | Pipeline 集成要求 Unity 6+；不能推导所有旧版本均兼容。不要自动添加包或改变项目设置 |
| unity-editor-mcp | Coplay Unity MCP，核对固定发布版、Python/uv 和对应 Editor 包；上游目前列出 Unity 2021.3–6.x。先 Inspector tools/list，核工程身份，再调用经审阅的只读工具 | 默认启用可能包含场景/资源写工具，必须限制实际可用工具与权限；不把 MCP 连接当路径沙箱 |

两项 integration.group 同为 unity-editor，最多启用一个；不并装以免重复命令和编辑竞争。不同项目可使用自己的既有适配器，记录真实 provider/来源/版本。连接和版本探测分别留证，缺少 Editor 或包时保持未配置。通用桥接不自动提供项目专属配表、事件图、导出器或业务菜单，仍在原 capabilities 注册实际工具。已有明确任务范围内的普通操作沿用授权；依赖安装、外传或跨界写入按实际规则处理。

## 来源与许可

核对日期：2026-10-17，安装时复核选定发布物。

- [Unity Test Framework CLI](https://docs.unity3d.com/Packages/com.unity.test-framework@1.4/manual/reference-command-line.html)；[Performance Testing](https://docs.unity3d.com/Packages/com.unity.test-framework.performance@3.2/manual/index.html) 和 [Measure.Method](https://docs.unity3d.com/Packages/com.unity.test-framework.performance@3.2/manual/measure-method.html)。文档版本是依据示例，目标工程选择兼容包；Unity 包/Editor 条款由其固定发布版提供。
- [Microsoft.Unity.Analyzers](https://github.com/microsoft/Microsoft.Unity.Analyzers)：MIT；本包不复制其诊断实现。
- [Unity Smart Merge](https://docs.unity3d.com/6000.0/Documentation/Manual/SmartMerge.html)、[Git LFS](https://git-lfs.com/) 与 [LFS 配置步骤](https://docs.github.com/en/repositories/working-with-files/managing-large-files/configuring-git-large-file-storage)：使用正式工具和项目既有策略。
- [Unity CLI](https://docs.unity.com/en-us/unity-cli/unity-cli-reference) 与 [Pipeline 要求](https://docs.unity.com/en-us/unity-cli/unity-pipeline/unity-pipeline-package)；[Coplay Unity MCP](https://github.com/CoplayDev/unity-mcp)（MIT）。不把实验性接口承诺为稳定/全版本通用能力。
