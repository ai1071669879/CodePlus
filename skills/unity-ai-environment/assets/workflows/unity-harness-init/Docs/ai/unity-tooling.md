# Harness 模式的 Unity 工具

<!-- ai-rule: unity-tooling -->

主执行通道固定为 Unity Skills REST；配置与验证顺序见 [workflow.md](workflow.md#harness-setup)。debug/test/console/validation/workflow 所需模块、权限与真实签名必须核对固定版本，不能用其它桥接替换。

`unity_checks.py` 的 NUnit XML、归一化性能预算、SARIF 和 meta/GUID 检查可由 Harness 合同明确引用为辅助证据；它不执行强制 REST 流程，不替代独立 Reviewer 或目标设备验收。可选 Editor gate 在此模式也不承担主执行职责。

<a id="unity-cli"></a>

## Unity CLI

目录仍可查看该工具的能力，但 Harness 选中时不能启用它代替 REST。若需要改为该提供者，先预览切换为 native 模式并处理状态/宿主冲突，再按 [官方 CLI 配置说明](https://docs.unity.com/en-us/unity-cli/use-unity-cli) 固定版本、接入 Pipeline、验证工程 status 与最小只读操作。

<a id="coplay"></a>

## Coplay MCP

在 native 模式选择 unity-editor-mcp 后，按 [Coplay 官方配置](https://github.com/CoplayDev/unity-mcp) 固定 server/Editor 包、审阅选定客户端配置、核 tools/list 与工程身份、执行最小只读验证。本模式不执行这套替代流程。

<a id="anklebreaker"></a>

## AnkleBreaker MCP

在 native 模式选择 unity-editor-anklebreaker 后，按 [AnkleBreaker 配置](https://github.com/AnkleBreaker-Studio/unity-mcp-server/blob/main/docs/configuration.md) 固定 server/plugin、审阅客户端 argv、发现并选择 Editor 身份，再按需取高级 schema。本模式不执行这套替代流程。

所有版本/连接/操作证据仍在 profile.capabilities，不因目录可见而设 verified。
