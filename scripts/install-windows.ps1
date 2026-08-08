# Domino Printer Middleware — Windows one-click installer
# Run via install.bat (self-elevates to Administrator)
#
# Default: LAN service on port 5003 (same network as Domino printer).
# Optional:  install.bat -WithCloudflare

param(
    [switch]$WithCloudflare,
    [switch]$SkipCloudflare
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
# Strip trailing slash for NSSM AppDirectory (avoids quote-escape bug)
$RootDir = $RootDir.TrimEnd('\')
$VenvDir = Join-Path $RootDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$SiteEnvPath = Join-Path $RootDir "config\site.env"
$SiteEnvExample = Join-Path $RootDir "config\site.env.example"
$PrintersExample = Join-Path $RootDir "config\printers.json.example"
$PrintersPath = Join-Path $RootDir "config\printers.json"
$LogsDir = Join-Path $RootDir "logs"
$ServiceName = "DominoPrinterMiddleware"
$CloudflaredService = "DominoCloudflared"
$ParentNssm = Join-Path (Split-Path $RootDir -Parent) "nssm.exe"
$LocalNssm = Join-Path $RootDir "nssm.exe"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Test-IsAdmin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ensure-Admin {
    if (Test-IsAdmin) { return }
    Write-Host "Requesting Administrator privileges..." -ForegroundColor Yellow
    $argsList = @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", "`"$PSCommandPath`"")
    if ($WithCloudflare) { $argsList += "-WithCloudflare" }
    if ($SkipCloudflare) { $argsList += "-SkipCloudflare" }
    Start-Process powershell.exe -Verb RunAs -ArgumentList $argsList -WorkingDirectory $RootDir
    exit 0
}

function Read-EnvFile([string]$Path) {
    $settings = @{}
    if (-not (Test-Path $Path)) { return $settings }
    foreach ($line in Get-Content $Path) {
        $trimmed = $line.Trim()
        if (-not $trimmed -or $trimmed.StartsWith("#")) { continue }
        $parts = $trimmed -split "=", 2
        if ($parts.Count -eq 2) { $settings[$parts[0].Trim()] = $parts[1].Trim() }
    }
    return $settings
}

function Find-Python {
    $candidates = @(
        (Get-Command python -ErrorAction SilentlyContinue)?.Source,
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "C:\Program Files\Python311\python.exe",
        "C:\Program Files\Python312\python.exe"
    ) | Where-Object { $_ -and (Test-Path $_) }
    foreach ($path in $candidates) {
        try {
            $version = & $path -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
            if ($version -and ([version]$version -ge [version]"3.8")) { return $path }
        } catch {
            continue
        }
    }
    return $null
}

function Ensure-Python {
    Write-Step "Checking Python 3.8+"
    $python = Find-Python
    if (-not $python) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            Write-Host "  Installing Python 3.11 via winget..."
            winget install -e --id Python.Python.3.11 --accept-package-agreements --accept-source-agreements --disable-interactivity
            Start-Sleep -Seconds 4
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                        [System.Environment]::GetEnvironmentVariable("Path", "User")
            $python = Find-Python
        }
    }
    if (-not $python) {
        throw "Python 3.8+ not found. Install from https://www.python.org/downloads/ (check 'Add to PATH')"
    }
    Write-Host "  OK: $python"
    return $python
}

function Ensure-Venv([string]$PythonPath) {
    Write-Step "Virtual environment and dependencies"
    if (-not (Test-Path $PythonExe)) {
        if (Test-Path $VenvDir) { Remove-Item $VenvDir -Recurse -Force }
        & $PythonPath -m venv $VenvDir
    }
    & $PythonExe -m pip install --upgrade pip
    & $PythonExe -m pip install -r (Join-Path $RootDir "requirements.txt")
    Write-Host "  OK: venv ready"
}

function Ensure-ConfigFiles {
    Write-Step "Configuration files"
    if (-not (Test-Path $SiteEnvPath) -and (Test-Path $SiteEnvExample)) {
        Copy-Item $SiteEnvExample $SiteEnvPath
        Write-Host "  Created site.env"
    }
    if (-not (Test-Path $PrintersPath) -and (Test-Path $PrintersExample)) {
        Copy-Item $PrintersExample $PrintersPath
        Write-Host "  Created printers.json — EDIT Domino IP before go-live"
    }
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

    # Local System service account needs read/write
    icacls $RootDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
    icacls $LogsDir /grant "SYSTEM:(OI)(CI)F" /T | Out-Null
    icacls (Join-Path $RootDir "config") /grant "SYSTEM:(OI)(CI)M" /T | Out-Null
}

function Ensure-Nssm {
    if (Test-Path $LocalNssm) { return $LocalNssm }
    if (Test-Path $ParentNssm) {
        Copy-Item $ParentNssm $LocalNssm -Force
        return $LocalNssm
    }
    $fromPath = Get-Command nssm -ErrorAction SilentlyContinue
    if ($fromPath) { return $fromPath.Source }

    Write-Step "Downloading NSSM"
    $zip = Join-Path $env:TEMP "nssm-2.24.zip"
    $dir = Join-Path $env:TEMP "nssm-2.24"
    $ProgressPreference = "SilentlyContinue"
    Invoke-WebRequest -Uri "https://nssm.cc/release/nssm-2.24.zip" -OutFile $zip
    if (Test-Path $dir) { Remove-Item $dir -Recurse -Force }
    Expand-Archive -Path $zip -DestinationPath $dir -Force
    $src = Join-Path $dir "nssm-2.24\win64\nssm.exe"
    if (-not (Test-Path $src)) { throw "NSSM download failed" }
    Copy-Item $src $LocalNssm -Force
    Write-Host "  OK: $LocalNssm"
    return $LocalNssm
}

function Install-MiddlewareService([hashtable]$Settings, [string]$Nssm) {
    Write-Step "Installing Windows service: $ServiceName"
    $port = if ($Settings.PORT) { $Settings.PORT } else { "5003" }
    $hostAddr = if ($Settings.HOST) { $Settings.HOST } else { "0.0.0.0" }

    & $Nssm stop $ServiceName 2>$null
    & $Nssm remove $ServiceName confirm 2>$null
    sc.exe delete $ServiceName 2>$null | Out-Null

    & $Nssm install $ServiceName $PythonExe
    & $Nssm set $ServiceName AppParameters "main.py --host $hostAddr --port $port"
    & $Nssm set $ServiceName AppDirectory $RootDir
    & $Nssm set $ServiceName DisplayName "Domino Printer Middleware"
    & $Nssm set $ServiceName Description "HTTP to Domino Ax Codenet TCP bridge for ERP"
    & $Nssm set $ServiceName Start SERVICE_AUTO_START
    & $Nssm set $ServiceName AppThrottle 1500
    & $Nssm set $ServiceName AppExit Default Restart
    & $Nssm set $ServiceName AppRestartDelay 5000
    & $Nssm set $ServiceName AppStdout (Join-Path $LogsDir "service-output.log")
    & $Nssm set $ServiceName AppStderr (Join-Path $LogsDir "service-error.log")
    & $Nssm set $ServiceName AppRotateFiles 1
    & $Nssm set $ServiceName AppRotateOnline 1
    & $Nssm set $ServiceName AppRotateBytes 10485760
    & $Nssm set $ServiceName AppNoConsole 1

    $envExtra = @(
        "PYTHONUNBUFFERED=1",
        "HOST=$hostAddr",
        "PORT=$port"
    )
    if ($Settings.API_KEY) { $envExtra += "API_KEY=$($Settings.API_KEY)" }
    if ($Settings.DOMINO_FIXED_ACK_MODE) { $envExtra += "DOMINO_FIXED_ACK_MODE=$($Settings.DOMINO_FIXED_ACK_MODE)" }
    & $Nssm set $ServiceName AppEnvironmentExtra ($envExtra -join "`n")

    sc.exe failure $ServiceName reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
    sc.exe failureflag $ServiceName 1 | Out-Null

    & $Nssm start $ServiceName
    Start-Sleep -Seconds 5

    $healthUri = "http://127.0.0.1:$port/health"
    $ok = $false
    for ($i = 1; $i -le 12; $i++) {
        try {
            $health = Invoke-RestMethod -Uri $healthUri -TimeoutSec 5
            if ($health.status -eq "healthy") {
                Write-Host "  OK: $healthUri -> $($health.status) ($($health.service))"
                $ok = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 3
        }
    }
    if (-not $ok) {
        throw "Health check failed at $healthUri. See logs\service-error.log"
    }
}

function Install-CloudflaredTunnel([hashtable]$Settings, [string]$Nssm) {
    Write-Step "Cloudflare tunnel (optional public URL)"
    if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
        if (Get-Command winget -ErrorAction SilentlyContinue) {
            winget install -e --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements --disable-interactivity
            $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                        [System.Environment]::GetEnvironmentVariable("Path", "User")
        } else {
            Write-Warning "cloudflared not found. Skipping public tunnel."
            return
        }
    }

    $hostname = if ($Settings.PUBLIC_HOSTNAME) { $Settings.PUBLIC_HOSTNAME } else { "domino-print.k95foods.com" }
    $port = if ($Settings.PORT) { $Settings.PORT } else { "5003" }
    $tunnelName = if ($Settings.TUNNEL_NAME) { $Settings.TUNNEL_NAME } else { "domino-print" }
    $cloudDir = Join-Path $HOME ".cloudflared"
    $configPath = Join-Path $cloudDir "config-domino.yml"

    New-Item -ItemType Directory -Force -Path $cloudDir | Out-Null
    if (-not (Test-Path $configPath)) {
        Write-Host "  One-time Cloudflare setup required:"
        Write-Host "    cloudflared tunnel login"
        Write-Host "    cloudflared tunnel create $tunnelName"
        Write-Host "    cloudflared tunnel route dns $tunnelName $hostname"
        @(
            "tunnel: REPLACE_WITH_TUNNEL_UUID",
            "credentials-file: $cloudDir\REPLACE.json",
            "ingress:",
            "  - hostname: $hostname",
            "    service: http://127.0.0.1:$port",
            "  - service: http_status:404"
        ) | Set-Content -Path $configPath -Encoding UTF8
        Write-Warning "Edit $configPath with tunnel UUID, then rerun: install.bat -WithCloudflare"
        return
    }

    $cf = (Get-Command cloudflared).Source
    & $Nssm stop $CloudflaredService 2>$null
    & $Nssm remove $CloudflaredService confirm 2>$null
    & $Nssm install $CloudflaredService $cf "tunnel --config `"$configPath`" run"
    & $Nssm set $CloudflaredService Start SERVICE_AUTO_START
    & $Nssm set $CloudflaredService AppExit Default Restart
    & $Nssm start $CloudflaredService
    Write-Host "  OK: $CloudflaredService -> https://$hostname"
}

# --- main ---
Ensure-Admin
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Domino Printer Middleware Installer" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Root: $RootDir"

if (-not (Test-Path (Join-Path $RootDir "main.py"))) {
    throw "main.py not found. Run installer from the domino folder."
}

Ensure-ConfigFiles
$python = Ensure-Python
Ensure-Venv $python
$nssm = Ensure-Nssm
$settings = Read-EnvFile $SiteEnvPath
Install-MiddlewareService $settings $nssm

$wantCf = $WithCloudflare -and (-not $SkipCloudflare)
if ($wantCf) {
    Install-CloudflaredTunnel $settings $nssm
} else {
    Write-Host ""
    Write-Host "  Cloudflare skipped (LAN mode). For public URL later:" -ForegroundColor Yellow
    Write-Host "    install.bat -WithCloudflare"
}

$port = if ($settings.PORT) { $settings.PORT } else { "5003" }
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Install complete" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Service:  $ServiceName"
Write-Host "  Local:    http://127.0.0.1:$port/health"
Write-Host "  Test:     POST http://127.0.0.1:$port/test/connection"
Write-Host ""
Write-Host "  NEXT: edit config\printers.json with real Domino IP, then:"
Write-Host "    curl -X POST http://127.0.0.1:$port/test/connection -H ""Content-Type: application/json"" -d ""{\""ip\"":\""DOMINO_IP\"",\""port\"":7000}"""
Write-Host ""
Write-Host "  Useful:"
Write-Host "    sc query $ServiceName"
Write-Host "    sc stop $ServiceName"
Write-Host "    sc start $ServiceName"
Write-Host "    uninstall.bat"
Write-Host ""
