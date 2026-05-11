param(
    [int]$DbPort = 5433,
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 5173,
    [string]$Dataset = "core_v1",
    [string]$PostgresBin,
    [string]$DatabaseUrl,
    [switch]$UseDockerDb,
    [switch]$SkipSeed,
    [switch]$SkipBackend,
    [switch]$SkipFrontend
)

$ErrorActionPreference = "Stop"

function Write-Step([string]$Message) {
    Write-Host "[prism-local] $Message" -ForegroundColor Cyan
}

function Test-PostgresBin([string]$Path) {
    if (-not $Path -or -not (Test-Path $Path)) {
        return $false
    }
    foreach ($exe in @("initdb.exe", "pg_ctl.exe", "pg_isready.exe", "createdb.exe", "psql.exe")) {
        if (-not (Test-Path (Join-Path $Path $exe))) {
            return $false
        }
    }
    return $true
}

function Resolve-PostgresBin([string]$ExplicitPath) {
    $candidates = @()
    if ($ExplicitPath) {
        $candidates += $ExplicitPath
    }
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
        if (Test-PostgresBin $candidate) {
            return $candidate
        }
    }

    throw @"
PostgreSQL command-line tools were not found.
Fix options:
  1. Pass -PostgresBin "C:\Program Files\PostgreSQL\16\bin" or set POSTGRES_BIN.
  2. Install PostgreSQL and add its bin directory to PATH.
  3. Run with -UseDockerDb only if you explicitly need the legacy Docker database.
  4. Pass -DatabaseUrl or set DATABASE_URL to use an existing database.
"@
}

function Resolve-DockerCmd {
    $command = Get-Command docker.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    $command = Get-Command docker -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }
    throw "Docker was not found. Install Docker Desktop or use -DatabaseUrl / -PostgresBin instead."
}

function Read-DotEnvValue([string]$Path, [string]$Key, [string]$DefaultValue) {
    if (-not (Test-Path $Path)) {
        return $DefaultValue
    }
    $line = Get-Content $Path -ErrorAction SilentlyContinue |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Key))\s*=" } |
        Select-Object -First 1
    if (-not $line) {
        return $DefaultValue
    }
    return ($line -replace "^\s*$([regex]::Escape($Key))\s*=\s*", "").Trim().Trim('"').Trim("'")
}

function Resolve-NpmCmd {
    $command = Get-Command npm.cmd -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    $fallback = "D:\nvm\nodejs\npm.cmd"
    if (Test-Path $fallback) {
        return $fallback
    }

    throw "npm.cmd not found. Install Node.js or add npm.cmd to PATH."
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
        Write-Step "Stopping existing $Label process ($($proc.Id))"
        Stop-Process -Id $proc.Id -Force
    } catch {
        Write-Step "No running $Label process found for pid file"
    } finally {
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
    }
}

function Wait-Http([string]$Url, [int]$TimeoutSeconds = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        try {
            $response = Invoke-WebRequest -Uri $Url -UseBasicParsing -TimeoutSec 5
            if ($response.StatusCode -ge 200 -and $response.StatusCode -lt 500) {
                return $true
            }
        } catch {
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

function Wait-Tcp([string]$HostName, [int]$Port, [int]$TimeoutSeconds = 30) {
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        $client = New-Object System.Net.Sockets.TcpClient
        try {
            $result = $client.BeginConnect($HostName, $Port, $null, $null)
            if ($result.AsyncWaitHandle.WaitOne(1000) -and $client.Connected) {
                $client.EndConnect($result)
                return $true
            }
        } catch {
        } finally {
            $client.Close()
        }
        Start-Sleep -Seconds 1
    }
    return $false
}

$repoRoot = Split-Path -Parent $PSScriptRoot
$backendDir = Join-Path $repoRoot "backend"
$backendPython = Join-Path $backendDir "venv\Scripts\python.exe"
$runtimeDir = Join-Path $backendDir ".runtime"
$pidDir = Join-Path $runtimeDir "pids"
$postgresDataDir = Join-Path $runtimeDir "postgres-data"
$postgresLogFile = Join-Path $runtimeDir "postgres.log"
$backendLogFile = Join-Path $runtimeDir "backend.dev.log"
$frontendLogFile = Join-Path $runtimeDir "frontend.dev.log"
$backendPidFile = Join-Path $pidDir "backend.pid"
$frontendPidFile = Join-Path $pidDir "frontend.pid"

if (-not (Test-Path $backendPython)) {
    throw "Backend virtualenv python was not found at '$backendPython'."
}

$npmCmd = Resolve-NpmCmd
$envDatabaseUrl = if ($DatabaseUrl) { $DatabaseUrl } elseif ($env:DATABASE_URL) { $env:DATABASE_URL } else { "" }
$databaseUrl = $envDatabaseUrl
$databaseDisplay = if ($databaseUrl) { "custom DATABASE_URL" } else { "postgresql://prism@localhost:$DbPort/prism_metabolic" }

New-Item -ItemType Directory -Force -Path $runtimeDir | Out-Null
New-Item -ItemType Directory -Force -Path $pidDir | Out-Null

if ($UseDockerDb) {
    $docker = Resolve-DockerCmd
    Write-Step "Starting legacy docker-compose PostgreSQL service"
    & $docker compose --profile legacy-db up -d db | Out-Host
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose up -d db failed. Ensure Docker Desktop is running, or pass -DatabaseUrl / POSTGRES_BIN for the unified local PostgreSQL instance."
    }
    if (-not (Wait-Tcp -HostName "127.0.0.1" -Port 5432 -TimeoutSeconds 45)) {
        throw "Docker PostgreSQL did not open localhost:5432 in time. Check 'docker compose logs db'."
    }
    $dbPassword = Read-DotEnvValue -Path (Join-Path $repoRoot ".env") -Key "DB_PASSWORD" -DefaultValue "prism_secure_password"
    $databaseUrl = "postgresql+asyncpg://postgres:$dbPassword@localhost:5432/prism_db"
    $databaseDisplay = "postgresql://postgres@localhost:5432/prism_db"
} elseif ($databaseUrl) {
    Write-Step "Using DATABASE_URL from environment/parameter"
} else {
    $postgresBin = Resolve-PostgresBin $PostgresBin
    $pgCtl = Join-Path $postgresBin "pg_ctl.exe"
    $pgIsReady = Join-Path $postgresBin "pg_isready.exe"
    $createdb = Join-Path $postgresBin "createdb.exe"
    $psql = Join-Path $postgresBin "psql.exe"
    $databaseUrl = "postgresql+asyncpg://prism:prism123@localhost:$DbPort/prism_metabolic"

    if (-not (Test-Path (Join-Path $postgresDataDir "PG_VERSION"))) {
        Write-Step "Initializing local PostgreSQL cluster in $postgresDataDir"
        & (Join-Path $postgresBin "initdb.exe") -D $postgresDataDir -U prism --auth-local=trust --auth-host=trust -E UTF8 --locale=C | Out-Host
    }

    & $pgIsReady -h localhost -p $DbPort -U prism *> $null
    if ($LASTEXITCODE -ne 0) {
        Write-Step "Starting local PostgreSQL on port $DbPort"
        & $pgCtl -D $postgresDataDir -l $postgresLogFile -o """-p $DbPort""" start | Out-Host
        Start-Sleep -Seconds 2
        & $pgIsReady -h localhost -p $DbPort -U prism | Out-Host
    }

    $dbExists = (& $psql -h localhost -p $DbPort -U prism -d postgres -tAc "select 1 from pg_database where datname = 'prism_metabolic';").Trim()
    if ($dbExists -ne "1") {
        Write-Step "Creating local database prism_metabolic"
        & $createdb -h localhost -p $DbPort -U prism prism_metabolic | Out-Host
    }
}

Write-Step "Running Alembic migrations"
Push-Location $backendDir
try {
    $env:DATABASE_URL = $databaseUrl
    & $backendPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) {
        throw "Alembic migration failed with exit code $LASTEXITCODE. Verify DATABASE_URL and PostgreSQL connectivity."
    }
    if (-not $SkipSeed) {
        Write-Step "Seeding knowledge dataset '$Dataset'"
        & $backendPython -m app.seed.knowledge_seed --dataset $Dataset
        if ($LASTEXITCODE -ne 0) {
            throw "Knowledge seed failed with exit code $LASTEXITCODE. Check the seed output above."
        }
    } else {
        Write-Step "Skipping knowledge seed"
    }
} finally {
    Pop-Location
}

Stop-ProcessFromPidFile -PidFile $backendPidFile -Label "backend"
Stop-ProcessFromPidFile -PidFile $frontendPidFile -Label "frontend"

if (-not $SkipBackend) {
    Write-Step "Starting backend on http://localhost:$BackendPort"
    $backendCommand = @"
`$env:DATABASE_URL = '$databaseUrl'
Set-Location '$backendDir'
& '$backendPython' -m uvicorn app.main:app --host 0.0.0.0 --port $BackendPort *>> '$backendLogFile'
"@
    $backendProc = Start-Process -FilePath "powershell.exe" -ArgumentList "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand -WindowStyle Hidden -PassThru
    $backendProc.Id | Set-Content $backendPidFile -Encoding ASCII
    if (-not (Wait-Http -Url "http://localhost:$BackendPort/api/health" -TimeoutSeconds 30)) {
        throw "Backend failed to become healthy on port $BackendPort. Check $backendLogFile"
    }
}

if (-not $SkipFrontend) {
    Write-Step "Starting frontend on http://localhost:$FrontendPort"
    $frontendCommand = @"
Set-Location '$repoRoot'
& '$npmCmd' run dev -- --host 0.0.0.0 --port $FrontendPort *>> '$frontendLogFile'
"@
    $frontendProc = Start-Process -FilePath "powershell.exe" -ArgumentList "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand -WindowStyle Hidden -PassThru
    $frontendProc.Id | Set-Content $frontendPidFile -Encoding ASCII
    if (-not (Wait-Http -Url "http://localhost:$FrontendPort" -TimeoutSeconds 45)) {
        throw "Frontend failed to become ready on port $FrontendPort. Check $frontendLogFile"
    }
}

Write-Step "Done"
Write-Host "Frontend: http://localhost:$FrontendPort"
Write-Host "Backend:  http://localhost:$BackendPort"
Write-Host "Docs:     http://localhost:$BackendPort/api/docs"
Write-Host "DB:       $databaseDisplay"
