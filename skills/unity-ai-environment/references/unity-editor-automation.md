# Unity 编辑器自动化（从本机会话提炼）

本页把三条真实 Unity 改造会话里反复出现的「操作已打开 Editor → 留证」模式固化为可复用工具。
工具随包提供，默认不启动 Editor、不改工程设置；只有在用户已授权且工程已打开时使用。

## 来源与会话事实

提炼自 2026-10-17、2026-10-21、2026-10-24 三个主会话及其子代理会话（thread id 前缀
`01a14928`、`01a15e3f`、`01a16cad`，共 63 个 rollout 文件）。这些会话里被反复手写的操作：

- 用 `Library/EditorInstance.json` 与进程列表确认当前 Editor 的 PID/工程/版本，避免连错实例；
- 已打开的 Editor 里起一个 `[InitializeOnLoad]` 的 Editor Gate，通过 `Temp/.../EditorGate/<pid>/`
  下的 `request.json`、`status.json`、`<id>/result.json` 做请求/回执，而不是点 UI；
- 每个请求使用唯一 id，先占目录再执行，拒绝覆盖既有证据；忙碌、编译、域重载都要显式处理；
- 批处理测试用 `-runTests -projectPath ... -testResults ... -logFile ...`，把 `TEMP/TMP`
  指到工程内临时目录，再用项目检查器解析 NUnit；
- Player 用独立进程启动，采集 stdout/stderr、退出码与超时后的进程树清理；
- 日志按 `error CS`、`Shader error`、异常、`Test run failed` 等分类留样，不把「进程退出 0」当通过。

这些会话里项目专属的 suite 名、截图脚本、业务采集代码**没有**复制进本包；本包只固化传输层、
发现、测试/Player/日志取证和证据规则。

## 文件

| 文件 | 作用 |
| --- | --- |
| `Editor/UnityEditorGate/UnityEditorGate.cs` | 可选 Editor 中继：轮询请求、调用工程内受权静态方法、写回执，处理域重载与忙碌 |
| `tools/ai/unity_editor.py` | 外部驱动器：`discover/status/request/wait/run/tests/player/log` |

安装（bootstrap apply）会把两者复制进目标工程；不需要时删除 `Editor/UnityEditorGate/`
并在任务记录中说明即可，不影响其他检查器。

## 快速用法（工程根执行）

```text
python tools/ai/unity_editor.py discover
python tools/ai/unity_editor.py status
python tools/ai/unity_editor.py run --id refresh-01 --suite refresh
python tools/ai/unity_editor.py run --id capture-01 --suite invoke \
    --type MyProject.EditorTools.SceneCapture --method Capture --arg map-01
python tools/ai/unity_editor.py wait --id capture-01 --timeout 600
python tools/ai/unity_editor.py tests --platform editmode
python tools/ai/unity_editor.py player --exe Builds/Windows/Game.exe --timeout 300
python tools/ai/unity_editor.py log "$env:LOCALAPPDATA/Unity/Editor/Editor.log" --require-clean
```

`--project` 可以是工程根，也可以是包含 `Docs/ai/project-profile.json` 的环境根（按
`unity.root` 解析）。`tests`/`player` 默认在工程的 `Temp/ai-unity-editor/` 下建立唯一证据目录；
`--dry-run` 只打印命令不执行。

退出码：`0` 成功/ready；`1` 运行失败、超时、测试失败、Player 非 0；`2` 用法或前置条件不满足。

## Gate 协议（schema_version 1）

根目录：`<project>/Temp/UnityEditorGate/<pid>/`。

```text
request.json          {"schema_version":1,"id":"<ascii>","suite":"refresh|wait-compile|invoke",
                       "type":"<Type>","method":"<static method>","args":["..."],"note":"..."}
status.json           最新回执：status=ready|busy|started|observed|failed, ok, id, suite, pid,
                      project, unity_version, ready, active, playing, compiling, updating,
                      error, rejected_request, updated_utc
<id>/request.json     被 gate 认领的请求（原子移入）
<id>/result.json      终态：ok, status, id, suite, result, error, started_utc, finished_utc；
                      被调用方法可在此目录追加自己的证据文件
rejected-*.json       被拒绝的请求（非法 id/suite、重复 id 等）+ error
allowlist.json        可选：{"methods":["Namespace.Type.Method", ...]}，存在时只允许列出的方法
```

`invoke` 只接受 `public static` 方法，签名支持 `()`、`(string runDirectory)`、
`(string[] args)`、`(string runDirectory, string[] args)`；返回值/`ToString()` 写入 result。

### 安全与授权

- gate 在 Editor 进程内执行工程代码，等价于项目开发者手动执行；只有任务明确授权时才调用，
  不把它当任意 shell。建议维护者启用 `allowlist.json` 收窄可调用方法。
- 不自动启动/杀死 Editor；driver 只按 `EditorInstance.json` 的 PID 定位。需要停止 Play/Editor
  时按用户指令显式操作，并保留证据。
- 同 id 永不覆盖；新证据换新 id。`status.json` 超过 `--stale-after` 视为陈旧。
- gate 只证明「请求被认领并返回结果」；`refresh` 不声称编译成功，`tests` 以 NUnit 报告与真实
  进程退出码为准，`invoke` 的语义由项目方法自己声明。

## 失败模式（会话中实际遇到）

| 现象 | 处理 |
| --- | --- |
| `status` 显示 `busy`（编译/导入/Play 切换） | `run` 默认先等 ready；超时则先 `log` 查编译错误，不重复发请求 |
| Play 中发 `refresh` | 可能触发脚本重载/退出 Play；先退出 Play 再刷新，或改用工程内 `invoke` 方法自行处理 |
| 域重载后旧请求消失 | gate 启动时把上次 `started` 标记为 `failed`（不再静默记住），换新 id 重试 |
| 重复 id / 已存在证据 | 拒绝执行；保留旧证据，改 id |
| Editor 被关闭或 PID 变化 | `discover` 复查 `EditorInstance.json` 与进程存活；新 PID 是新 gate 根 |
| 测试进程退出 0 但报告缺失 | 判失败；检查授权/编译/平台依赖，不能用退出码冒充通过 |
| Player 超时 | 终止进程树并保留 stdio/日志；不把超时当通过 |

## 与现有检查器的分工

`unity_editor.py tests` 只负责**运行与留证**，NUnit 解析仍调用 `unity_checks.py tests`（拒绝损坏/
未知状态/失败/零执行等），避免第二套判定口径。`unity_checks.py` 的资产检查、`baseline.py`
的盘点、`check_env.py check` 的门禁仍各自独立，互不替代。

## 未固化项（按项目自行实现）

- 项目专属 suite/白名单、画面采集与截图脚本、业务诊断入口：留在工程内，通过 `invoke` 调用。
- 构建产物：用 `invoke` 调用工程自己的 `BuildPipeline`/发布方法，本包不内置构建参数。
- Roslyn 离线编译检查：会话中从目标 Editor 的 `app_contents_path` 加载编译器做预检；该做法依赖
  Editor 安装与版本，按项目需要自行实现，本包不假设路径。
- 窗口激活、点击与人工 UI 操作：不自动化；需要时由操作者执行并记录观察结果。
- 多 Editor 并存：driver 只按 `EditorInstance.json`/`--pid` 定位，不枚举并猜测；需要多实例时
  各自用独立 gate 根与 id 命名空间。

## 维护与验证

模板更新后至少做三步：Python 语法与 `tests/test_unity_editor.py` 黑盒测试；用目标 Editor 的
引用程序集编译 C# 模板（例如 Unity 2022.3 的 `UnityEditor.dll` + `UnityEngine.CoreModule.dll`
/ `UnityEngine.JSONSerializeModule.dll`，`csc -target:library`）；在真实工程打开 Editor，
确认 `<project>/Temp/UnityEditorGate/<pid>/status.json` 出现 `ready` 且 `discover`/`status`
能对上 PID。编译通过只证明语法/引用，不替代 Editor 导入、域重载与运行时行为验证。
