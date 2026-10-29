<#
sync-config.ps1 —— 把本机 Codex **全局环境**快照进 CodePlus（live -> 仓库）。

只管全局环境：docs/CODEX-SETUP.md、codex/AGENTS.global.md、codex/agents/*.toml。
项目技能不在这里处理——用 tools/sync-skills.ps1（严格分离）。

三步：
  1. sync-guide.py            live 配置 -> docs/CODEX-SETUP.md 与 docs/CODEX-AGENTS-TEMPLATES.md
  2. 快照 live -> codex/      ~/.codex/AGENTS.md、~/.codex/agents/*.toml
  3. check-consistency.py     跨文件规则一致性

反方向（仓库 -> live）用 `tools/install-codex-env.ps1`。

用法（本机是 Windows PowerShell 5.1，用 powershell 而不是 pwsh）：
    powershell -NoProfile -File <repo>\tools\sync-config.ps1
    powershell -NoProfile -File <repo>\tools\sync-config.ps1 -Preview
#>
param(
    [switch]$Preview,
    [switch]$SkipCodex
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$home_dir = $env:USERPROFILE
$codex_dir = Join-Path $home_dir '.codex'
$py = 'python'
$failures = New-Object System.Collections.Generic.List[string]

function Copy-IfChanged([string]$source, [string]$target) {
    if (-not (Test-Path $source)) { return 'missing-live' }
    if ((Test-Path $target) -and
        (Get-FileHash $source -Algorithm SHA256).Hash -eq (Get-FileHash $target -Algorithm SHA256).Hash) {
        return 'same'
    }
    if (-not $Preview) {
        New-Item -ItemType Directory -Force (Split-Path -Parent $target) | Out-Null
        Copy-Item $source $target -Force
    }
    return 'updated'
}

Write-Host '=== 1/3 同步 live 配置 -> 指南 ===' -ForegroundColor Cyan
if ($Preview) {
    & $py -X utf8 (Join-Path $PSScriptRoot 'sync-guide.py')
} else {
    & $py -X utf8 (Join-Path $PSScriptRoot 'sync-guide.py') --write
}
$syncExit = $LASTEXITCODE
if ($syncExit -ne 0) { $failures.Add("sync-guide exit=$syncExit（live 配置缺失或指南写入失败）") }

if (-not $SkipCodex) {
    Write-Host ''
    Write-Host '=== 2/3 快照 live -> codex/ ===' -ForegroundColor Cyan
    $agent_files = @(Get-ChildItem (Join-Path $codex_dir 'agents') -Filter *.toml -ErrorAction SilentlyContinue)
    if ($agent_files.Count -eq 0) {
        $failures.Add('live 里找不到 ~/.codex/agents/*.toml（目录缺失或为空）')
    }
    $rows = @()
    $rows += [pscustomobject]@{ File = 'codex/AGENTS.global.md'; State = (Copy-IfChanged (Join-Path $codex_dir 'AGENTS.md') (Join-Path $repo 'codex\AGENTS.global.md')) }
    $agent_files | ForEach-Object {
        $rows += [pscustomobject]@{ File = "codex/agents/$($_.Name)"; State = (Copy-IfChanged $_.FullName (Join-Path $repo "codex\agents\$($_.Name)")) }
    }
    $rows | ForEach-Object {
        "  {0,-34} {1}" -f $_.File, $_.State
        if ($_.State -eq 'missing-live') { $failures.Add("live 缺失：$($_.File)（仓库保留旧快照）") }
    }
}

Write-Host ''
Write-Host '=== 3/3 一致性校验 ===' -ForegroundColor Cyan
& $py -X utf8 (Join-Path $PSScriptRoot 'check-consistency.py')
$checkExit = $LASTEXITCODE
if ($checkExit -ne 0) { $failures.Add("check-consistency exit=$checkExit") }

Write-Host ''
if ($failures.Count -eq 0) {
    if ($Preview) { Write-Host '预览完成：guide 与一致性已检查，未写入任何文件。' -ForegroundColor Green }
    else { Write-Host '完成：guide 已同步，codex/ 已是 live 快照，一致性通过。' -ForegroundColor Green }
    Write-Host '提示：agents/*.toml 与 config.toml 在 Codex 启动时读取，改动后需重启 Codex。' -ForegroundColor DarkGray
    exit 0
}
Write-Host ("失败 {0} 项：" -f $failures.Count) -ForegroundColor Red
$failures | ForEach-Object { Write-Host ('  - ' + $_) -ForegroundColor Red }
exit 1
