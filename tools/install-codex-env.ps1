<#
install-codex-env.ps1 —— 把 CodePlus 的 **Codex 全局环境**安装到本机（仓库 -> live）。

只安装全局环境：
  codex/AGENTS.global.md   ->  <HOME>\.codex\AGENTS.md
  codex/agents\*.toml      ->  <HOME>\.codex\agents\
项目技能不在这里处理——用 tools/install-skills.ps1（严格分离）。

**不触碰** config.toml、auth.json、sessions、plugins 等运行时数据；config.toml 含机器特定
MCP 路径，按 docs\CODEX-SETUP.md §3.2 自行维护。

安全策略：默认预览，`-Apply` 才写入；写入前备份到 <HOME>\.codex-backups\<时间戳>-codeplus\。

用法：
    powershell -NoProfile -File <repo>\tools\install-codex-env.ps1            # 预览
    powershell -NoProfile -File <repo>\tools\install-codex-env.ps1 -Apply     # 写入
#>
param([switch]$Apply)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$home_dir = $env:USERPROFILE
$codex_dir = Join-Path $home_dir '.codex'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup_root = Join-Path $home_dir ".codex-backups\$stamp-codeplus"

if (-not (Test-Path (Join-Path $codex_dir 'config.toml'))) {
    Write-Host '警告：<HOME>\.codex\config.toml 不存在。本脚本不创建 config.toml——先按指南 §3.2 配置。' -ForegroundColor Yellow
}

$agentsDir = Join-Path $repo 'codex\agents'
$agentFiles = @(Get-ChildItem $agentsDir -Filter *.toml -ErrorAction SilentlyContinue)
if (-not (Test-Path (Join-Path $repo 'codex\AGENTS.global.md'))) {
    Write-Host '仓库不完整：缺少 codex\AGENTS.global.md，拒绝安装。' -ForegroundColor Red
    exit 1
}
if ($agentFiles.Count -eq 0) {
    Write-Host '仓库不完整：codex\agents\ 下没有任何 *.toml，拒绝安装。' -ForegroundColor Red
    exit 1
}

$plan = New-Object System.Collections.Generic.List[object]
function Add-Plan([string]$source, [string]$target) {
    if (-not (Test-Path $source)) { $plan.Add([pscustomobject]@{ Source = $source; Target = $target; State = 'missing-source' }); return }
    if (-not (Test-Path $target)) { $plan.Add([pscustomobject]@{ Source = $source; Target = $target; State = 'new' }); return }
    $same = (Get-FileHash $source -Algorithm SHA256).Hash -eq (Get-FileHash $target -Algorithm SHA256).Hash
    $plan.Add([pscustomobject]@{ Source = $source; Target = $target; State = $(if ($same) { 'same' } else { 'update' }) })
}
function Backup-Target([string]$target) {
    if (-not (Test-Path $target)) { return }
    $relative = $target.Substring($home_dir.Length).TrimStart('\')
    $destination = Join-Path $backup_root $relative
    New-Item -ItemType Directory -Force (Split-Path -Parent $destination) | Out-Null
    Copy-Item $target $destination -Recurse -Force
}

Add-Plan (Join-Path $repo 'codex\AGENTS.global.md') (Join-Path $codex_dir 'AGENTS.md')
$agentFiles | ForEach-Object { Add-Plan $_.FullName (Join-Path $codex_dir "agents\$($_.Name)") }

Write-Host '=== 安装计划（仓库 -> live）===' -ForegroundColor Cyan
foreach ($item in $plan) {
    $relative = $item.Target.Substring($home_dir.Length).TrimStart('\')
    "{0,-52} {1}" -f $relative, $item.State
}
$missing = @($plan | Where-Object { $_.State -eq 'missing-source' })
$changes = @($plan | Where-Object { $_.State -in @('new', 'update') })
$same = @($plan | Where-Object { $_.State -eq 'same' })
Write-Host ''
Write-Host ("需要写入：{0} 项；相同跳过：{1} 项；源缺失：{2} 项" -f $changes.Count, $same.Count, $missing.Count)
if ($missing.Count -gt 0) {
    Write-Host '源缺失，拒绝执行（仓库不完整；先修复仓库快照）：' -ForegroundColor Red
    $missing | ForEach-Object { Write-Host ('  - ' + $_.Source) -ForegroundColor Red }
    exit 1
}
if (-not $Apply) {
    Write-Host ''
    Write-Host '预览模式：未写入任何文件。加 -Apply 执行。' -ForegroundColor Yellow
    exit 0
}
if ($changes.Count -eq 0) { Write-Host '已是最新，无需写入。' -ForegroundColor Green; exit 0 }

foreach ($item in $changes) {
    Backup-Target $item.Target
    New-Item -ItemType Directory -Force (Split-Path -Parent $item.Target) | Out-Null
    Copy-Item $item.Source $item.Target -Force
}
Write-Host ''
Write-Host ("已安装 {0} 项；备份在 {1}" -f $changes.Count, $backup_root) -ForegroundColor Green
Write-Host '**重启 Codex** 后生效：~/.codex/AGENTS.md 与 agents/*.toml 在启动时读取。' -ForegroundColor DarkGray
Write-Host '安装后建议在 CodePlus 运行 tools/sync-config.ps1 与 tools/sync-skills.ps1 复核。' -ForegroundColor DarkGray
exit 0
