# CI 与强制检查接入

初始化不自动修改远端配置、安装钩子或注入令牌。先明确托管平台、可信操作者、可信策略版本、比较基线，以及修改/删除/重命名路径的获取方式，再编写目标平台配置。

## 最小可执行检查

在目标项目根执行：

```text
python -B tools/ai/check_env.py check
python -B tools/ai/check_env.py scope --user <trusted-actor> --paths <changed-relative-path> ...
```

第一条只校验规则、项目事实、导航和任务结构。第二条在 audit 下输出越界但不失败，在 enforce 下越界退出 1。非法路径始终失败。没有待检查路径时显式记录空变更集，不拼出一条缺参数的命令。

项目工程门禁使用 profile 中已经核实的 build/test/lint 入口分别配置为 job；检查器不会执行它们。AI 代码审查可另加非阻断 job，但不代替测试或授权。

## 可信执行要求

- PR/MR 作者和推送者身份从托管平台可信事件或 API 获得，不能来自提交里的 JSON、可伪造环境文件或 git user.name。CI 用户名到项目账号要明确映射。
- 权限检查器与 policy 从受保护目标分支或其他可信版本读取，防止变更同时放宽自己的规则；待审工作树的修改不能控制安全门禁。
- 用真实比较基线收集全部变更路径，覆盖删除和重命名的旧/新路径；通过参数数组调用，保留空格/非 ASCII 文件名，不经 shell eval。
- 将 check/scope 命令的原始退出码传给管线；不使用吞掉错误的后置命令。必要时确认 job 是保护分支的必需状态检查。
- 客户端 pre-commit/pre-push 只辅助反馈，可被绕过；CI 在推送后执行，不能撤销已经入库的提交。确需在推送前强制拒绝时，由管理员部署受信任的服务端机制并实测。

## 验收记录

用一个允许路径变更和一个越界变更实际触发管线，记录 actor、策略修订、比较基线、检查输出及退出码，再决定 enforce 和必需状态检查。未执行前在 profile 保持 server_enforcement=not_configured 或 not_tested；不将 YAML 存在表述为服务器已拦截。


## 可选质量门禁

从项目根按实际采用的能力接入：`environment.py doctor --probe` 做固定版本探测，`evaluate.py validate` 验用例结构，`evaluate.py score --observations <真实运行观察>` 验行为证据，`quality.py architecture --graph <真实图> --expected-revision <检出修订>` 验约束，`quality.py secrets --paths <明确范围>` 做本地脱敏扫描。这些命令不能互相替代，也不取代真实构建/测试。

先把实际门禁命令登记在 profile 或项目既有 CI；未配置项不要假装已启用。0 表示各自范围通过，1 为失败，提供未配置/未验证状态的工具使用 2；作为必需门禁时所有非零都失败，不使用 `|| true` 隐藏。性能/依赖输入与受保护策略来自可信步骤，核对代码修订和运行环境；归一化报告要保留原件、生成命令和工具版本。扫描配置/严重级别/预算不能由受检查变更自行放宽。

Unity 可加 `unity_checks.py tests --report <XML> --exit-code <实际码>`、`performance --samples <JSON> --baseline <可比基线>`、`diagnostics --report <SARIF>` 及明确资源范围的 `assets --paths ...`。只适用于选择 Unity 包的项目。先运行真实工具再解释报告；空报告、全跳过、缺分析器执行证明都不能当成功。构建/测试源不因门禁失败而降标准。


核心摘要预算与基线结构随 `check_env.py check` 校验。需要检查源码相对初始化基线的漂移时使用 `baseline.py compare`；退出1意味着差异，需要按变更预期复核，并非所有差异都是缺陷。基线刷新不是自动合并规则或扩大授权；不要把更新快照作为掩盖未验变更的手段。
