# Harness 模式合同入口

该模式采用已导入并核验的 `.github/templates/task-contract.md`，规划、文件分区、依赖、TDD 和独立验收均按 [workflow.md](workflow.md) 执行。

原生 Keep/Rewrite 契约不是此模式的强制前置，`contract_check.py` 不参与默认阶段。确有额外重构限制时，由 Harness 合同显式引用所需机器判据；额外检查不能替代 REST 流程或凭据/范围/最终接受要求。
