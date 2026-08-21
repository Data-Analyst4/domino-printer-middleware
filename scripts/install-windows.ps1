# Domino Printer Middleware - Windows one-click installer
# Run via install.bat (self-elevates to Administrator)
#
# Default: middleware service + Cloudflare public URL when possible.
# LAN-only:  install.bat -SkipCloudflare

param(
    [switch]$WithCloudflare,
    [switch]$SkipCloudflare
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$RootDir = $RootDir.TrimEnd('\')
$VenvDir = Join-Path $RootDir ".venv"
$PythonExe = Join-Path $VenvDir "Scripts\python.exe"
$SiteEnvPath = Join-Path $RootDir "config\site.env"
$SiteEnvExample = Join-Path $RootDir "config\site.env.example"
$PrintersExample = Join-Path $RootDir "config\printers.json.example"
$PrintersDemo = Join-Path $RootDir "config\printers.demo.json"
$PrintersPath = Join-Path $RootDir "config\printers.json"
$LogsDir = Join-Path $RootDir "logs"
$ServiceName = "DominoPrinterMiddleware"
$CloudflaredService = "DominoCloudflared"
$ParentNssm = Join-Path (Split-Path $RootDir -Parent) "nssm.exe"
$LocalNssm = Join-Path $RootDir "nssm.exe"

# Cloudflare ON by default (use -SkipCloudflare for LAN-only)
$EnableCloudflare = -not $SkipCloudflare
if ($WithCloudflare) { $EnableCloudflare = $true }

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
    $pyCmd = Get-Command python -ErrorAction SilentlyContinue
    $candidates = @(
        $(if ($pyCmd) { $pyCmd.Source } else { $null }),
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
    if (-not (Test-Path $PrintersPath)) {
        if (Test-Path $PrintersExample) {
            Copy-Item $PrintersExample $PrintersPath
            Write-Host "  Created printers.json - EDIT Domino IP before go-live"
        } elseif (Test-Path $PrintersDemo) {
            Copy-Item $PrintersDemo $PrintersPath
            Write-Host "  Created printers.json from demo (127.0.0.1)"
        }
    }
    New-Item -ItemType Directory -Force -Path $LogsDir | Out-Null

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

function Stop-PortListeners([int]$Port) {
    try {
        $conns = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
        foreach ($c in $conns) {
            $procId = $c.OwningProcess
            if ($procId -and $procId -ne 0) {
                $proc = Get-Process -Id $procId -ErrorAction SilentlyContinue
                if ($proc -and $proc.ProcessName -match 'python|cloudflared') {
                    Write-Host "  Stopping $($proc.ProcessName) (PID $procId) on port $Port"
                    Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
                }
            }
        }
    } catch {
        # Best-effort; service install will fail clearly if port stays busy
    }
}

function Find-Cloudflared {
    $cmd = Get-Command cloudflared -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
    $candidates = @(
        "${env:ProgramFiles(x86)}\cloudflared\cloudflared.exe",
        "$env:ProgramFiles\cloudflared\cloudflared.exe",
        "$env:LOCALAPPDATA\Programs\cloudflared\cloudflared.exe"
    )
    foreach ($p in $candidates) {
        if (Test-Path $p) { return $p }
    }
    return $null
}

function Ensure-CloudflaredBinary {
    $cf = Find-Cloudflared
    if ($cf) { return $cf }

    Write-Step "Installing cloudflared"
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Write-Warning "winget not found - cannot install cloudflared automatically"
        return $null
    }
    winget install -e --id Cloudflare.cloudflared --accept-package-agreements --accept-source-agreements --disable-interactivity
    $env:Path = [System.Environment]::GetEnvironmentVariable("Path", "Machine") + ";" +
                [System.Environment]::GetEnvironmentVariable("Path", "User")
    Start-Sleep -Seconds 2
    return (Find-Cloudflared)
}

function Get-TunnelIdFromList([string]$Cloudflared, [string]$TunnelName) {
    $raw = & $Cloudflared tunnel list 2>$null | Out-String
    foreach ($line in ($raw -split "`r?`n")) {
        if ($line -match "^([0-9a-f-]{36})\s+$([regex]::Escape($TunnelName))\s+") {
            return $Matches[1]
        }
    }
    return $null
}

function Ensure-DominoTunnelConfig([hashtable]$Settings, [string]$Cloudflared) {
    $hostname = if ($Settings.ContainsKey("PUBLIC_HOSTNAME") -and $Settings["PUBLIC_HOSTNAME"]) { $Settings["PUBLIC_HOSTNAME"] } else { "domino-print.k95foods.com" }
    $port = if ($Settings.ContainsKey("PORT") -and $Settings["PORT"]) { $Settings["PORT"] } else { "5003" }
    $tunnelName = if ($Settings.ContainsKey("TUNNEL_NAME") -and $Settings["TUNNEL_NAME"]) { $Settings["TUNNEL_NAME"] } else { "domino-print" }
    $cloudDir = Join-Path $HOME ".cloudflared"
    $configPath = Join-Path $cloudDir "config-domino.yml"
    $certPath = Join-Path $cloudDir "cert.pem"

    New-Item -ItemType Directory -Force -Path $cloudDir | Out-Null

    # Reuse existing good config
    if (Test-Path $configPath) {
        $existing = Get-Content $configPath -Raw
        if ($existing -notmatch "REPLACE_WITH_TUNNEL_UUID" -and $existing -match "tunnel:\s*([0-9a-f-]{36})") {
            Write-Host "  OK: using existing $configPath"
            return @{ ConfigPath = $configPath; Hostname = $hostname; Port = $port }
        }
    }

    if (-not (Test-Path $certPath)) {
        Write-Warning "Cloudflare login missing ($certPath)."
        Write-Host "  One-time:  cloudflared tunnel login"
        Write-Host "  Then rerun: install.bat"
        return $null
    }

    Write-Step "Ensuring Cloudflare tunnel '$tunnelName'"
    $tunnelId = Get-TunnelIdFromList $Cloudflared $tunnelName
    if (-not $tunnelId) {
        Write-Host "  Creating tunnel $tunnelName ..."
        & $Cloudflared tunnel create $tunnelName 2>&1 | Out-Host
        $tunnelId = Get-TunnelIdFromList $Cloudflared $tunnelName
    }
    if (-not $tunnelId) {
        Write-Warning "Could not create/find tunnel '$tunnelName'"
        return $null
    }

    $credFile = Join-Path $cloudDir "$tunnelId.json"
    if (-not (Test-Path $credFile)) {
        Write-Warning "Credentials missing: $credFile"
        Write-Host "  Delete the tunnel in Cloudflare Zero Trust and rerun install, or copy credentials JSON here."
        return $null
    }

    Write-Host "  Routing DNS $hostname -> $tunnelName"
    & $Cloudflared tunnel route dns $tunnelName $hostname 2>&1 | Out-Host

    $yaml = @"
tunnel: $tunnelId
credentials-file: $credFile
ingress:
  - hostname: $hostname
    service: http://127.0.0.1:$port
  - service: http_status:404
"@
    Set-Content -Path $configPath -Value $yaml -Encoding UTF8
    Write-Host "  OK: wrote $configPath"
    return @{ ConfigPath = $configPath; Hostname = $hostname; Port = $port }
}

function Install-MiddlewareService([hashtable]$Settings, [string]$Nssm) {
    Write-Step "Installing Windows service: $ServiceName"
    $port = if ($Settings.ContainsKey("PORT") -and $Settings["PORT"]) { $Settings["PORT"] } else { "5003" }
    $hostAddr = if ($Settings.ContainsKey("HOST") -and $Settings["HOST"]) { $Settings["HOST"] } else { "0.0.0.0" }

    Stop-PortListeners ([int]$port)

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
    if ($Settings.ContainsKey("API_KEY") -and $Settings["API_KEY"]) { $envExtra += "API_KEY=$($Settings['API_KEY'])" }
    if ($Settings.ContainsKey("DOMINO_FIXED_ACK_MODE") -and $Settings["DOMINO_FIXED_ACK_MODE"]) {
        $envExtra += "DOMINO_FIXED_ACK_MODE=$($Settings['DOMINO_FIXED_ACK_MODE'])"
    }
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
    Write-Step "Cloudflare public URL (one-click)"
    $cf = Ensure-CloudflaredBinary
    if (-not $cf) {
        Write-Warning "cloudflared not available - middleware still installed for LAN use"
        return $null
    }
    Write-Host "  cloudflared: $cf"

    $info = Ensure-DominoTunnelConfig $Settings $cf
    if (-not $info) {
        Write-Warning "Cloudflare tunnel not configured - middleware still installed for LAN use"
        return $null
    }

    $configPath = $info.ConfigPath
    $hostname = $info.Hostname

    & $Nssm stop $CloudflaredService 2>$null
    & $Nssm remove $CloudflaredService confirm 2>$null
    sc.exe delete $CloudflaredService 2>$null | Out-Null

    & $Nssm install $CloudflaredService $cf
    & $Nssm set $CloudflaredService AppParameters "tunnel --config `"$configPath`" run"
    & $Nssm set $CloudflaredService AppDirectory (Split-Path $cf -Parent)
    & $Nssm set $CloudflaredService DisplayName "Domino Cloudflare Tunnel"
    & $Nssm set $CloudflaredService Description "Public HTTPS tunnel for Domino Printer Middleware"
    & $Nssm set $CloudflaredService Start SERVICE_AUTO_START
    & $Nssm set $CloudflaredService AppExit Default Restart
    & $Nssm set $CloudflaredService AppRestartDelay 5000
    & $Nssm set $CloudflaredService AppStdout (Join-Path $LogsDir "cloudflared-output.log")
    & $Nssm set $CloudflaredService AppStderr (Join-Path $LogsDir "cloudflared-error.log")
    & $Nssm set $CloudflaredService AppRotateFiles 1
    & $Nssm set $CloudflaredService AppNoConsole 1

    sc.exe failure $CloudflaredService reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
    sc.exe failureflag $CloudflaredService 1 | Out-Null

    & $Nssm start $CloudflaredService
    Start-Sleep -Seconds 4

    $public = "https://$hostname/health"
    $ok = $false
    for ($i = 1; $i -le 15; $i++) {
        try {
            $health = Invoke-RestMethod -Uri $public -TimeoutSec 8
            if ($health.status -eq "healthy") {
                Write-Host "  OK: $public"
                $ok = $true
                break
            }
        } catch {
            Start-Sleep -Seconds 2
        }
    }
    if (-not $ok) {
        Write-Warning "Public health not ready yet (DNS may still propagate). Local service is fine."
        Write-Host "  Try later: $public"
    }
    return $hostname
}

# --- main ---
Ensure-Admin

$InstallLog = Join-Path $RootDir "logs\install.log"
New-Item -ItemType Directory -Force -Path (Split-Path $InstallLog) | Out-Null
Start-Transcript -Path $InstallLog -Append | Out-Null
try {
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Domino Printer Middleware - One-Click Install" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Root: $RootDir"
Write-Host "  Cloudflare: $(if ($EnableCloudflare) { 'ON (default)' } else { 'OFF (-SkipCloudflare)' })"

if (-not (Test-Path (Join-Path $RootDir "main.py"))) {
    throw "main.py not found. Run installer from the repo root."
}

Ensure-ConfigFiles
$python = Ensure-Python
Ensure-Venv $python
$nssm = Ensure-Nssm
$settings = Read-EnvFile $SiteEnvPath
Install-MiddlewareService $settings $nssm

$publicHost = $null
if ($EnableCloudflare) {
    $publicHost = Install-CloudflaredTunnel $settings $nssm
} else {
    Write-Host ""
    Write-Host "  Cloudflare skipped (LAN mode)." -ForegroundColor Yellow
}

$port = if ($settings.ContainsKey("PORT") -and $settings["PORT"]) { $settings["PORT"] } else { "5003" }
Write-Host ""
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Install complete" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Green
Write-Host "  Service:     $ServiceName  (auto-start + auto-restart)"
Write-Host "  Local:       http://127.0.0.1:$port/health"
if ($publicHost) {
    Write-Host "  Cloudflare:  $CloudflaredService  (auto-start + auto-restart)"
    Write-Host "  Public:      https://$publicHost/health"
} else {
    Write-Host "  Public:      (not configured - rerun install.bat after cloudflared tunnel login)"
}
Write-Host ""
Write-Host "  NEXT: edit config\printers.json with real Domino IP (port 7000)"
Write-Host "  Uninstall: uninstall.bat"
Write-Host ""
} catch {
    Write-Host ""
    Write-Host "[ERROR] $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "See log: $InstallLog"
    throw
} finally {
    Stop-Transcript | Out-Null
}
