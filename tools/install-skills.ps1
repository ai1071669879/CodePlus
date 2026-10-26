<#
install-skills.ps1 —— 把 CodePlus 仓库里的两个项目技能装到本机（仓库 -> live）。

与 Codex 全局环境完全分开：只写 `~/.codex/skills/<name>/`，不碰 AGENTS.md / agents / config.toml。
全局环境安装用 tools/install-codex-env.ps1。

用法：
    powershell -NoProfile -File <repo>\tools\install-skills.ps1            # 预览
    powershell -NoProfile -File <repo>\tools\install-skills.ps1 -Apply     # 写入（先备份）
#>
param(
    [switch]$Apply,
    [string[]]$Only = @('project-ai-environment', 'unity-ai-environment')
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$home_dir = $env:USERPROFILE
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$backup_root = Join-Path $home_dir ".codex-backups\$stamp-codeplus-skills"

function Get-TreeHash([string]$directory) {
    if (-not (Test-Path $directory)) { return '' }
    $entries = Get-ChildItem $directory -Recurse -File -ErrorAction SilentlyContinue |
        Where-Object { $_.FullName -notmatch '__pycache__|\.pytest_cache|test-runs' } |
        Sort-Object FullName |
        ForEach-Object {
            $relative = $_.FullName.Substring($directory.Length).TrimStart('\')
            "$relative|$((Get-FileHash $_.FullName -Algorithm SHA256).Hash)"
        }
    $bytes = [System.Text.Encoding]::UTF8.GetBytes([string]::Join("`n", $entries))
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { [System.BitConverter]::ToString($sha.ComputeHash($bytes)).Replace('-', '') }
    finally { $sha.Dispose() }
}

$plan = New-Object System.Collections.Generic.List[object]
foreach ($name in $Only) {
    $source = Join-Path $repo "skills\$name"
    $target = Join-Path $home_dir ".codex\skills\$name"
    if (-not (Test-Path $source)) { $plan.Add([pscustomobject]@{ Name = $name; Source = $source; Target = $target; State = 'missing-source' }); continue }
    if (-not (Test-Path $target)) { $plan.Add([pscustomobject]@{ Name = $name; Source = $source; Target = $target; State = 'new' }); continue }
    $same = (Get-TreeHash $source) -eq (Get-TreeHash $target)
    $plan.Add([pscustomobject]@{ Name = $name; Source = $source; Target = $target; State = $(if ($same) { 'same' } else { 'update' }) })
}

Write-Host '=== 项目技能：仓库 -> live ===' -ForegroundColor Cyan
foreach ($item in $plan) { "  {0,-26} {1}" -f $item.Name, $item.State }
$missing = @($plan | Where-Object { $_.State -eq 'missing-source' })
$changes = @($plan | Where-Object { $_.State -in @('new', 'update') })
$same = @($plan | Where-Object { $_.State -eq 'same' })
Write-Host ''
Write-Host ("需要安装：{0} 项；相同跳过：{1} 项；源缺失：{2} 项" -f $changes.Count, $same.Count, $missing.Count)
if ($missing.Count -gt 0) {
    Write-Host '仓库缺少 skill，拒绝安装：' -ForegroundColor Red
    $missing | ForEach-Object { Write-Host ('  - ' + $_.Source) -ForegroundColor Red }
    exit 1
}
if (-not $Apply) {
    Write-Host ''
    Write-Host '预览模式：未写入任何文件。加 -Apply 执行。' -ForegroundColor Yellow
    exit 0
}
if ($changes.Count -eq 0) { Write-Host '已是最新，无需安装。' -ForegroundColor Green; exit 0 }

foreach ($item in $changes) {
    if (Test-Path $item.Target) {
        $backup = Join-Path $backup_root "skills\$($item.Name)"
        New-Item -ItemType Directory -Force (Split-Path -Parent $backup) | Out-Null
        Copy-Item $item.Target $backup -Recurse -Force
    }
    New-Item -ItemType Directory -Force (Split-Path -Parent $item.Target) | Out-Null
    $null = robocopy $item.Source $item.Target /MIR /XD __pycache__ .pytest_cache test-runs /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) { Write-Host ("安装失败：{0} (robocopy exit={1})" -f $item.Name, $LASTEXITCODE) -ForegroundColor Red; exit 1 }
}
Write-Host ''
Write-Host ("已安装 {0} 项；备份在 {1}" -f $changes.Count, $backup_root) -ForegroundColor Green
exit 0
