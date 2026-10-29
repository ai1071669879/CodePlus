# 初始化、适配与维护

## 先核实事实

定位用户授权的环境根与实际工程根，读取已有入口、权限和工程说明，记录分支/HEAD/已有改动。无Git时不自行建仓库。确认维护者、身份来源、代码/资源/生成物目录、敏感职责及已有构建/测试/CI；只发现路径和命令不代表已运行。顺便发现本项目已有的skills清单，文件可见不等于平台已加载。

目标已有制度和用户明确要求优先适配；新增授权交维护者登记，不把初始样板角色或口头岗位当成写入范围。未确认内容留空并列出待接入项，继续不依赖它的只读准备。

## 预览和初始化

使用本包scripts/bootstrap.py，从任意工作目录传入明确的--project。先plan，可加--diff审阅候选内容，再apply。目标根必须已存在；脚本不联网、不装插件、不改模型或Git配置、不运行工程命令。

生成的完整内容就在assets/project。根AGENTS使用包内完整核心模板，不在生成后再压缩或改写为口号；项目大小写/路径适配须保留全部核心含义，并按配置合同审阅、真实核计及更新证书。平台按需选择codex/claude/cursor/trae/workbuddy/opencode或all；AGENTS保留500 token内核心摘要，各平台入口转读同一权威规则。已有入口文字保留；不同内容的受管配置冲突时整批不写，不删除后重装。

## 填写与使用

配置字段只在 [随包配置合同](../assets/project/Docs/ai/configuration.md) 维护；安装到项目后读取Docs/ai/configuration.md。按真实事实填写profile/context，由维护者登记policy；不要把源项目表直接复制成新项目授权。

回读实际写入的根AGENTS，并确认check中根入口core_matches=true且预算通过；不能只凭短文本或已刷新manifest判定完成。执行check与whoami，已登记成员可用identity缓存本人，换人/冲突按配置合同处理，clear-identity只清缓存。check报告规则路由、项目技能发现、导航时效、任务修订/验收和能力问题；scope检查候选路径。工程门禁单独运行。

对所选平台开新会话，用一个小只读任务核对实际读取、身份/权限和导航。没有行为证据时保持runtime_load=not_tested。CI和服务端按ci-integration.md另行接入，不能把文件存在当作强制检查已上线。

## 更新已有环境

比较plan --diff和包内相应资产，保留原授权、负责人、状态、历史及更严格规则，逐文件人工合并后check。新版本新增rules.json/configuration.md等文件时先补权威入口，合并schema的新可选字段；不以新模板清空现有数据。

generated_paths统一留在profile；旧policy同名字段仅作为迁移警告。Unity能力状态集中在capabilities，Unity字段只引用能力ID。真实个性化变更造成快照摘要变化只警告，不自动覆盖。

## 验收

交付生成/合并/冲突清单、真实身份来源、已填事实、仍未配置的能力，以及命令/退出码。静态、编译、运行、性能、平台加载和服务器执行分开记录。外部工程与远端服务各自核对授权；初始化不替它们授予权限。


## 质量与工具扩展的初始化

环境检查通过后，在目标根运行 `python tools/ai/environment.py doctor`、`python tools/ai/environment.py modules` 和 `python tools/ai/evaluate.py validate`。三者不启动模型/工程/网络服务。新建工程已带评测集、空架构策略和 Gitleaks 配置；空架构/性能预算属于待配置，不能列作工程门禁成功。

C1–C5 首批内容已经部署，外部扫描器/Inspector 仍需按 [工具接入](../assets/project/Docs/ai/tool-integrations.md) 选版本和启用；C6–C8 保持按需。Unity 的 U2–U4 检查器也只读取真实报告/选择的资源，U1 需按专页接入。先实测再填写 verified 状态，不靠文件存在升级。

升级已有工程时，plan 先输出冲突和候选 diff。对新增文档/脚本逐项合并；已有 profile 保留项目能力 ID、状态、命令和授权，仅添加确实采用的 integration 字段。更新规则路由、受管文件记录和薄入口后重新 check。不要用重置 manifest/权限或删除配置来规避冲突。


## 全面静态盘点与语义适配

初始化必须执行包内 plan/apply 的自动全树扫描，不仅套用模板。读取扫描摘要和project-adaptation中的证据，核对已有规则、各技术栈关键入口、模块依赖、声明门禁、生成器与职责缺项，再根据真实项目合并规则和事实。二进制不读取全文；内置规则识别的凭据/缓存/外部链接不读取内容（未识别形态须显式排除）；所有排除、超限、解析失败和未知项均报告。不得把扫描成功称为业务语义审查、源码可达、编译或运行通过。

两份新产物project-baseline.json/project-adaptation.md和500 token证书随完整事务写入；超预算/已有定制冲突时不发生部分写入。原有较长AGENTS不能自动压缩覆盖；先展示具体冲突及拟迁移的条款，保留核心边界，把详细流程合并到真实权威正文后再核计。普通后续任务定向读取，不反复全扫。

升级旧环境需把baseline.py/entry_budget.py及证书、adaptation路由一起合并。全扫描仅提供静态来源，人工维护者授权继续独立核对；新检测到目录不自动扩权限。无可证构建命令时保持未配置；新入口的500 token不能通过换成“只读其他文件”的空摘要达成。
