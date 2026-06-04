# auto_push.ps1 - submodule-aware auto-commit + push to GitHub (cloud backup).
#
# Invoked by auto_push.bat via Windows Task Scheduler. Fully non-interactive.
# Commits any uncommitted work in each agent submodule AND the parent repo, then
# pushes everything (parent + submodule commits) to their own remotes.
#
#   -DryRun : log what WOULD happen; make no commits and no push (leaves the
#             working tree exactly as found). Use to validate before scheduling.
#
# Why commit AND push: a commit is local - it dies with the drive. Only a push
# is a backup. This is the fix for the 2026-06-03 loss.
param([switch]$DryRun)

$ErrorActionPreference = 'Continue'
$repo = 'E:\options_scanner'
Set-Location $repo

$logDir = Join-Path $repo 'logs'
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir | Out-Null }
$log   = Join-Path $logDir 'auto_push.log'
$stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
function Write-Log($msg) { Add-Content -Path $log -Value "[$stamp] $msg" }

# Files that must NEVER be auto-committed, even if .gitignore develops a hole.
# (Belt-and-suspenders: these are already gitignored; this guards the auto-push
# path specifically, since a bad commit would publish instantly and unattended.)
$secretPattern = '(^|/)(credentials\.json|config\.json|gmail_token\.json|client_secret_[^/]*\.json)$|\.db(-wal|-shm)?$'

function Commit-IfChanged($label) {
    git add -A 2>$null
    $staged = git diff --cached --name-only
    if (-not $staged) { return }                       # nothing to commit
    $bad = $staged | Where-Object { $_ -match $secretPattern }
    if ($bad) {
        Write-Log "SECRET GUARD ($label): refusing to commit -> $($bad -join ', ')"
        git reset -q 2>$null
        return
    }
    if ($DryRun) {
        Write-Log "[dry-run] would commit $(@($staged).Count) file(s) in ${label}: $($staged -join ', ')"
        git reset -q 2>$null
        return
    }
    git commit -q -m "auto-backup $stamp" 2>&1 | Out-Null
    Write-Log "committed $(@($staged).Count) file(s) in $label"
}

Write-Log "==== auto-push run start $(if ($DryRun) {'(DRY RUN)'} else {''}) ===="

$submodules = 'system_analyst','trading_advisor','market_analyst','earnings_researcher','roundtable'
foreach ($s in $submodules) {
    $path = Join-Path $repo "agents\$s"
    if (-not (Test-Path $path)) { Write-Log "skip: missing submodule agents/$s"; continue }
    Push-Location $path
    git symbolic-ref -q HEAD *> $null                  # detect detached HEAD
    if ($LASTEXITCODE -ne 0) {
        git checkout -q master 2>$null
        Write-Log "agents/$s was detached -> checked out master"
    }
    Commit-IfChanged "agents/$s"
    Pop-Location
}

# Parent last, so it records any updated submodule pointers.
Commit-IfChanged "parent"

if ($DryRun) {
    Write-Log "[dry-run] would: git push --recurse-submodules=on-demand origin master"
} else {
    git push --recurse-submodules=on-demand origin master *>> $log
    if ($LASTEXITCODE -eq 0) { Write-Log "push OK" }
    else { Write-Log "PUSH FAILED (exit $LASTEXITCODE) - see git output above" }
}
Write-Log "==== auto-push run end ===="
