<#
sync-skills.ps1 —— 把本机已安装的两个项目技能镜像进 CodePlus 仓库（live -> 仓库）。

与 Codex 全局环境完全分开：本脚本只碰 `~/.codex/skills/<name>/` 与仓库 `skills/<name>/`。
Codex 全局配置（AGENTS.md / agents / config.toml / 指南）不在这里处理，用 tools/sync-config.ps1。

用法：
    powershell -NoProfile -File <repo>\tools\sync-skills.ps1
    powershell -NoProfile -File <repo>\tools\sync-skills.ps1 -Preview
    powershell -NoProfile -File <repo>\tools\sync-skills.ps1 -Only project-ai-environment
#>
param(
    [switch]$Preview,
    [string[]]$Only = @('project-ai-environment', 'unity-ai-environment')
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$home_dir = $env:USERPROFILE
$failures = New-Object System.Collections.Generic.List[string]

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

Write-Host '=== 项目技能：live -> 仓库 ===' -ForegroundColor Cyan
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
foreach ($name in $Only) {
    $source = Join-Path $home_dir ".codex\skills\$name"
    $target = Join-Path $repo "skills\$name"
    if (-not (Test-Path $source)) { "  {0,-26} missing-live (skipped)" -f $name; $failures.Add("live 缺失 skill：$name"); continue }
    if ((Get-TreeHash $source) -eq (Get-TreeHash $target)) { "  {0,-26} same" -f $name; continue }
    if ($Preview) { "  {0,-26} drift (would mirror)" -f $name; continue }
    if (Test-Path $target) {
        $backup = Join-Path $repo "backups\$stamp\skills\$name"
        New-Item -ItemType Directory -Force (Split-Path -Parent $backup) | Out-Null
        Copy-Item $target $backup -Recurse -Force
    }
    $null = robocopy $source $target /MIR /XD __pycache__ .pytest_cache test-runs /NFL /NDL /NJH /NJS /NP
    if ($LASTEXITCODE -ge 8) { $failures.Add("robocopy failed for $name (exit=$LASTEXITCODE)"); continue }
    $count = (Get-ChildItem $target -Recurse -File | Measure-Object).Count
    "  {0,-26} mirrored ({1} files; 仓库侧旧内容备份到 backups\{2})" -f $name, $count, $stamp
}

Write-Host ''
if ($failures.Count -gt 0) {
    Write-Host ("失败 {0} 项：" -f $failures.Count) -ForegroundColor Red
    $failures | ForEach-Object { Write-Host ('  - ' + $_) -ForegroundColor Red }
    exit 1
}
if ($Preview) { Write-Host '预览完成：未写入任何文件。' -ForegroundColor Green } else { Write-Host '完成：skills/ 已是 live 镜像。' -ForegroundColor Green }
exit 0
