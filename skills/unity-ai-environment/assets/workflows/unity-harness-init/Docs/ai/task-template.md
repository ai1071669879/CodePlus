# Harness 合同与接力入口

本模式的任务合同使用已核验的 `.github/templates/task-contract.md`，运行时合同保存在 `docs/harness/contracts/`；当前状态唯一在 `docs/harness/progress.md`，不登记到 Tasks/index.json。

Tasks 仅存分支/执行者的接力笔记，记录任务/合同链接、分支及源码修订、dirty 范围、执行者、导航 ID、决定/证据指针、已运行与未运行检查、下一条动作和验收。由 Coordinator 从 progress 链接，不复制任务状态，不覆写另一执行者笔记。具体规则见 [workflow.md](workflow.md)。
