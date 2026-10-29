<#
verify-repo.ps1 —— 本机一致性校验（**依赖 ~/.codex 现状**）。

它验证「这台机器上的 live 环境」与「仓库快照」一致，分两块，**互不混用**：
  A. Codex 全局环境（AGENTS.md / agents / 指南 / gudie 一致性）
  B. 项目技能（仓库收录 skill 的镜像与安装计划）

新克隆/新机器上必然有若干项失败，正确顺序是先 install-codex-env.ps1 -Apply 与
install-skills.ps1 -Apply，再跑本脚本。因此**不要把它接进没有 live 配置的 CI**。

检查项：
  1. tools/*.ps1 都是 UTF-8 with BOM（PowerShell 5.1 的硬要求）
  2. tools/*.py 能编译（py_compile）
  3. 仓库卫生：没有 __pycache__ / .pytest_cache / *.pyc
  4. 仓库内文档的相对链接都存在
  5. [全局] live 配置 -> 指南 已一致（sync-config -Preview exit 0 且无 [同步]）
  6. [全局] 仓库 -> live 安装计划为空（install-codex-env exit 0 且 0 项变更）
  7. [全局] codex/ 与本机逐文件哈希一致
  8. [技能] 仓库技能双向一致（sync-skills 无 drift；install-skills 计划为空）

用法：
    powershell -NoProfile -File <repo>\tools\verify-repo.ps1
退出码：0 全部通过；1 有失败项（明细逐条打印）。
#>
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$home_dir = $env:USERPROFILE
$failures = New-Object System.Collections.Generic.List[string]

function Pass([string]$name) { Write-Host ("  [PASS] " + $name) -ForegroundColor Green }
function Fail([string]$name, [string]$detail) {
    Write-Host ("  [FAIL] " + $name + " :: " + $detail) -ForegroundColor Red
    $script:failures.Add($name)
}
function Get-TreeHash([string]$directory) {
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

Write-Host '1/8 PowerShell 脚本编码（UTF-8 BOM）' -ForegroundColor Cyan
Get-ChildItem (Join-Path $PSScriptRoot '*.ps1') | ForEach-Object {
    $bytes = [System.IO.File]::ReadAllBytes($_.FullName)
    $bom = $bytes.Length -ge 3 -and $bytes[0] -eq 0xEF -and $bytes[1] -eq 0xBB -and $bytes[2] -eq 0xBF
    if ($bom) { Pass $_.Name } else { Fail $_.Name 'missing UTF-8 BOM' }
}

Write-Host '2/8 Python 脚本可编译' -ForegroundColor Cyan
# 用 AST 解析而不是 py_compile：后者会写 __pycache__（py_compile 不遵守 -B），
# 校验脚本不应删除或新增仓库里的字节码缓存。
Get-ChildItem (Join-Path $PSScriptRoot '*.py') | ForEach-Object {
    & python -X utf8 -c "import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8-sig'))" $_.FullName
    if ($LASTEXITCODE -eq 0) { Pass $_.Name } else { Fail $_.Name 'syntax check failed' }
}

Write-Host '3/8 仓库卫生（无字节码缓存）' -ForegroundColor Cyan
# backups/ 是同步脚本的本地回滚产物、.git/ 是版本库元数据：两者都不随仓库发布，
# 不应因为其中含有缓存就让本机校验失败。
$caches = @(Get-ChildItem $repo -Recurse -Force -Directory -ErrorAction SilentlyContinue |
    Where-Object { ($_.FullName -notlike '*\backups\*') -and ($_.FullName -notlike '*\.git\*') -and ($_.Name -in @('__pycache__', '.pytest_cache')) })
$pyc = @(Get-ChildItem $repo -Recurse -Force -File -Filter '*.pyc' -ErrorAction SilentlyContinue |
    Where-Object { ($_.FullName -notlike '*\backups\*') -and ($_.FullName -notlike '*\.git\*') })
if ($caches.Count -eq 0 -and $pyc.Count -eq 0) { Pass 'no cache residue' }
else { Fail 'no cache residue' ("dirs=$($caches.Count) pyc=$($pyc.Count); 删除后重跑") }

Write-Host '4/8 文档相对链接' -ForegroundColor Cyan
& python -X utf8 (Join-Path $PSScriptRoot 'check-links.py')
if ($LASTEXITCODE -eq 0) { Pass 'check-links.py' } else { Fail 'check-links.py' 'broken links' }

Write-Host '5/8 [全局] live 配置 -> 指南（快照已一致）' -ForegroundColor Cyan
$preview = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'sync-config.ps1') -Preview 2>&1 | Out-String
$previewExit = $LASTEXITCODE
if ($previewExit -ne 0) { Fail 'sync-config -Preview' "exit=$previewExit（live 配置缺失或一致性失败）" }
elseif ($preview -match '\[同步\]') { Fail 'sync-config -Preview' 'found pending [同步]; run sync-config.ps1' }
else { Pass 'sync-config -Preview' }

Write-Host '6/8 [全局] 仓库 -> live（安装计划为空）' -ForegroundColor Cyan
$install = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install-codex-env.ps1') 2>&1 | Out-String
$installExit = $LASTEXITCODE
if ($installExit -ne 0) { Fail 'install-codex-env preview' "exit=$installExit" }
elseif ($install -match '需要写入：0 项') { Pass 'install-codex-env preview' }
else { Fail 'install-codex-env preview' 'repo and live differ; run install or sync first' }

Write-Host '7/8 [全局] codex/ 与本机一致' -ForegroundColor Cyan
$pairs = New-Object System.Collections.Generic.List[object]
$pairs.Add([pscustomobject]@{ Name = 'AGENTS.md'; Repo = (Join-Path $repo 'codex\AGENTS.global.md'); Live = (Join-Path $home_dir '.codex\AGENTS.md') })
Get-ChildItem (Join-Path $repo 'codex\agents') -Filter *.toml | ForEach-Object {
    $pairs.Add([pscustomobject]@{ Name = "agents/$($_.Name)"; Repo = $_.FullName; Live = (Join-Path $home_dir ".codex\agents\$($_.Name)") })
}
foreach ($pair in $pairs) {
    if (-not (Test-Path $pair.Live)) { Fail $pair.Name 'missing live file'; continue }
    if ((Get-FileHash $pair.Repo -Algorithm SHA256).Hash -eq (Get-FileHash $pair.Live -Algorithm SHA256).Hash) { Pass $pair.Name }
    else { Fail $pair.Name 'hash differs from live' }
}

Write-Host '8/8 [技能] 仓库技能双向一致' -ForegroundColor Cyan
$skillSync = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'sync-skills.ps1') -Preview 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Fail 'sync-skills -Preview' "exit=$LASTEXITCODE" }
elseif ($skillSync -match 'drift') { Fail 'sync-skills -Preview' 'skill drift between live and repo; run sync-skills.ps1' }
else { Pass 'sync-skills -Preview' }
$skillInstall = & powershell -NoProfile -ExecutionPolicy Bypass -File (Join-Path $PSScriptRoot 'install-skills.ps1') 2>&1 | Out-String
if ($LASTEXITCODE -ne 0) { Fail 'install-skills preview' "exit=$LASTEXITCODE" }
elseif ($skillInstall -match '需要安装：0 项') { Pass 'install-skills preview' }
else { Fail 'install-skills preview' 'repo skills differ from live; run install-skills.ps1 -Apply' }
foreach ($name in @('project-ai-environment', 'unity-ai-environment', 'design-patterns')) {
    $repoDir = Join-Path $repo "skills\$name"
    $liveDir = Join-Path $home_dir ".codex\skills\$name"
    if (-not (Test-Path $liveDir)) { Fail "skills/$name" 'missing live skill'; continue }
    if ((Get-TreeHash $repoDir) -eq (Get-TreeHash $liveDir)) { Pass "skills/$name" }
    else { Fail "skills/$name" 'tree hash differs from live' }
}

Write-Host ''
if ($failures.Count -eq 0) {
    Write-Host '全部通过：本机 live 环境与仓库快照一致（全局环境 + 项目技能）。' -ForegroundColor Green
    exit 0
}
Write-Host ("失败 {0} 项（本脚本依赖本机 ~/.codex；新机器先跑 install-codex-env.ps1 -Apply 与 install-skills.ps1 -Apply）：" -f $failures.Count) -ForegroundColor Red
$failures | ForEach-Object { Write-Host ("  - " + $_) -ForegroundColor Red }
exit 1
