param(
    [int]$DbPort = 5433
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "[prism-local] $Message" -ForegroundColor Cyan
}

function Resolve-PostgresBin {
    $candidates = @()
    if ($env:POSTGRES_BIN) {
        $candidates += $env:POSTGRES_BIN
    }
    foreach ($commandName in @("pg_ctl.exe", "pg_ctl")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command) {
            $candidates += (Split-Path -Parent $command.Source)
        }
    }
    foreach ($root in @("C:\Program Files\PostgreSQL", "C:\PostgreSQL", "D:\PostgreSQL", "D:\SQL")) {
        if (Test-Path $root) {
            $versions = Get-ChildItem $root -Directory -ErrorAction SilentlyContinue | Sort-Object Name -Descending
            foreach ($version in $versions) {
                $candidates += (Join-Path $version.FullName "bin")
            }
            $candidates += (Join-Path $root "bin")
        }
    }

    foreach ($candidate in ($candidates | Where-Object { $_ } | Select-Object -Unique)) {
        if (
            (Test-Path (Join-Path $candidate "pg_ctl.exe")) -and
            (Test-Path (Join-Path $candidate "pg_isready.exe"))
        ) {
            return $candidate
        }
    }

    throw "PostgreSQL command-line tools were not found. Set POSTGRES_BIN if you need to stop the script-managed local database."
}

function Stop-ProcessFromPidFile([string]$PidFile, [string]$Label) {
    if (-not (Test-Path $PidFile)) {
        return
    }

    $rawPid = Get-Content $PidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $rawPid) {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        return
    }

    try {
        $proc = Get-Process -Id ([int]$rawPid) -ErrorAction Stop
        Write-Step "Stopping $Label process ($($proc.Id))"
        Stop-Process -Id $proc.Id -Force
    } catch {
        Write-Step "$Label process already stopped"
    } finally {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$runtimeDir = Join-Path $backendDir ".runtime"
$pidDir = Join-Path $runtimeDir "pids"
$postgresDataDir = Join-Path $runtimeDir "postgres-data"
$backendPidFile = Join-Path $pidDir "backend.pid"
$frontendPidFile = Join-Path $pidDir "frontend.pid"

Stop-ProcessFromPidFile -PidFile $backendPidFile -Label "backend"
Stop-ProcessFromPidFile -PidFile $frontendPidFile -Label "frontend"

if (Test-Path (Join-Path $postgresDataDir "PG_VERSION")) {
    $postgresBin = Resolve-PostgresBin
    $pgCtl = Join-Path $postgresBin "pg_ctl.exe"
    $pgIsReady = Join-Path $postgresBin "pg_isready.exe"
    & $pgIsReady -h localhost -p $DbPort -U prism *> $null
    if ($LASTEXITCODE -eq 0) {
        Write-Step "Stopping local PostgreSQL on port $DbPort"
        & $pgCtl -D $postgresDataDir stop | Out-Host
    } else {
        Write-Step "Local PostgreSQL is not running on port $DbPort"
    }
}

Write-Step "Done"
