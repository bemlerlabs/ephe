<#
  Ephe installer for Windows (PowerShell). macOS and Linux use install.sh.

  One-command install: clones/updates the checkout, prepares Python, builds the PWA
  and starts the local server on http://127.0.0.1:<Port>. The AI engine is chosen in
  the app afterwards — this script installs neither Ollama nor a model (mandate
  2026-08-21).

  Env (same names as install.sh): EPHE_INSTALL_DIR, EPHE_PORT, EPHE_MODE,
  EPHE_NO_START, EPHE_DRY_RUN, EPHE_REPO_URL, EPHE_OLLAMA_HOST.
#>
[CmdletBinding()]
param(
  [string]$InstallDir,
  [string]$Port,
  [switch]$NoStart,
  [switch]$Cli,
  [switch]$Desktop,
  [switch]$DryRun,
  [Alias("h")][switch]$Help
)

$ErrorActionPreference = "Stop"

# install.sh runs under `set -e`, so a failing command stops it. PowerShell does NOT
# throw on a non-zero native exit, so every native call goes through Run() below,
# which turns a non-zero $LASTEXITCODE into a terminating error.
$script:DryRun = $false
$script:VendorTmp = $null

# First-run diagnosability: an unexpected terminating error names itself instead of
# stopping the run in silence (parity with install.sh's ERR trap). The finally-style
# cleanup drops a vendor temp file even when the run is interrupted.
trap {
  [Console]::Error.WriteLine("  install.ps1 failed: $($_.Exception.Message)")
  if ($script:VendorTmp -and (Test-Path -LiteralPath $script:VendorTmp)) {
    Remove-Item -Force -LiteralPath $script:VendorTmp -ErrorAction SilentlyContinue
  }
  exit 1
}

function Step([string]$Text) { Write-Host "`n> $Text" -ForegroundColor Green }
function Ok([string]$Text) { Write-Host "  OK $Text" -ForegroundColor Green }
function Warn([string]$Text) { Write-Host "  WARN $Text" -ForegroundColor Yellow }
function Info([string]$Text) { Write-Host "  $Text" -ForegroundColor DarkGray }
function Fail([string]$Text) { [Console]::Error.WriteLine("  FAIL $Text"); exit 1 }

# Runs a native command, honouring the dry run and failing on a non-zero exit.
function Run([string]$Label, [scriptblock]$Command) {
  if ($script:DryRun) { Info "DRY-RUN: $Label"; return }
  & $Command
  if ($LASTEXITCODE -ne 0) { throw "$Label failed (exit $LASTEXITCODE)." }
}

if ($Help) {
  Write-Host "Usage: install.ps1 [-InstallDir <path>] [-Port <1-65535>] [-Cli|-Desktop] [-NoStart] [-DryRun]"
  Write-Host "Env:   EPHE_INSTALL_DIR, EPHE_PORT, EPHE_MODE, EPHE_NO_START, EPHE_DRY_RUN"
  Write-Host ""
  Write-Host "Ephe - one-command install. The AI engine is chosen in the app"
  Write-Host "(local Ollama or an external endpoint such as DGX)."
  Write-Host "Ollama is NOT installed and NO models are downloaded."
  Write-Host ""
  Write-Host "  -Cli       Minimal CLI path: installs only the TUI (textual), starts 'ephe tui'"
  Write-Host "  -Desktop   (default) Desktop/PWA: installs gui+voice, starts 'ephe start --open'"
  Write-Host ""
  Write-Host "Without a mode switch the installer asks interactively when a console is available."
  exit 0
}

# Resolve flags and environment, then refuse a bad environment.
# A wrong EPHE_PORT used to reach the app's own argument parser and an unknown
# EPHE_MODE used to fall through to the desktop branch, so both are checked here,
# where the message can still name the value that was wrong (parity with install.sh).
$RepoUrl = if ($env:EPHE_REPO_URL) { $env:EPHE_REPO_URL } else { "https://github.com/bemlerlabs/ephe.git" }
$OllamaHost = if ($env:EPHE_OLLAMA_HOST) { $env:EPHE_OLLAMA_HOST } else { "127.0.0.1:11434" }
$OllamaUrl = if ($OllamaHost -notmatch '^https?://') { "http://$OllamaHost" } else { $OllamaHost }

if (-not $InstallDir) {
  $InstallDir = if ($env:EPHE_INSTALL_DIR) { $env:EPHE_INSTALL_DIR } else { Join-Path $HOME "Documents/Ephe" }
}

if ($env:EPHE_NO_START -eq "1") { $NoStart = $true }
if ($env:EPHE_DRY_RUN -eq "1") { $DryRun = $true }
$script:DryRun = [bool]$DryRun

$PortValue = if ($Port) { $Port } elseif ($env:EPHE_PORT) { $env:EPHE_PORT } else { "8765" }
if ($PortValue -notmatch '^\d+$' -or [int]$PortValue -lt 1 -or [int]$PortValue -gt 65535) {
  [Console]::Error.WriteLine("EPHE_PORT must be a port number between 1 and 65535, got '$PortValue'.")
  exit 2
}
$Port = [int]$PortValue

# Mode selection: switch > env > interactive > default(desktop).
$Mode = $null
if ($Cli) { $Mode = "cli" }
elseif ($Desktop) { $Mode = "desktop" }
elseif ($env:EPHE_MODE) { $Mode = $env:EPHE_MODE }
if (-not $Mode) {
  if (-not $script:DryRun -and -not $NoStart -and [Environment]::UserInteractive -and $Host.Name -eq 'ConsoleHost') {
    $choice = Read-Host "How do you want to use Ephe? [D]esktop/PWA, [C]li (TUI), or [S]kip-start"
    switch -Regex ($choice) {
      '^[Cc]' { $Mode = "cli" }
      '^[Ss]' { $NoStart = $true; $Mode = "desktop" }
      default { $Mode = "desktop" }
    }
  } else {
    $Mode = "desktop"
  }
}
if ($Mode -notin @("cli", "desktop")) {
  [Console]::Error.WriteLine("EPHE_MODE must be 'cli' or 'desktop', got '$Mode'.")
  exit 2
}
$Cli = ($Mode -eq "cli")

Write-Host ""
Write-Host "Ephe offline-first installer" -ForegroundColor Green
Write-Host "One-command install. The AI engine is chosen in the app (local Ollama or an external endpoint)." -ForegroundColor DarkGray

# Free space (GB) on the drive the repo sits on. -1 when it cannot be read.
function Get-FreeSpaceGB {
  try {
    $letter = (Get-Location).Path.Substring(0, 1)
    # ${letter}, not $letter: inside a double-quoted string PowerShell reads `$letter:'`
    # as a scope-qualified variable and refuses to parse the whole file — "Variable
    # reference is not valid. ':' was not followed by a valid variable name character".
    # Nothing in the repository could run this installer (2026-10-09, found by
    # tests/test_installer_cli.py, which is the gate that actually parses).
    $vol = Get-CimInstance Win32_LogicalDisk -Filter "DeviceID='${letter}:'" -ErrorAction SilentlyContinue
    if ($vol) { return [math]::Floor($vol.FreeSpace / 1GB) }
  } catch { }
  return -1
}

function Test-ProjectRoot {
  (Test-Path -LiteralPath (Join-Path $PWD "pyproject.toml")) -and
    (Test-Path -LiteralPath (Join-Path $PWD "app/src")) -and
    (Test-Path -LiteralPath (Join-Path $PWD "run_server.py"))
}

if (-not (Test-ProjectRoot)) {
  Step "Preparing the install folder"
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Fail "Git is missing. Install Git for Windows and run this script again."
  }
  $Parent = Split-Path $InstallDir -Parent
  # A dry run reports the clone it would run instead of creating folders for it.
  if (-not $script:DryRun) { New-Item -ItemType Directory -Force -Path $Parent | Out-Null }
  if (Test-Path -LiteralPath (Join-Path $InstallDir ".git")) {
    Ok "Existing repository found: $InstallDir"
    Set-Location $InstallDir
    try {
      Run "git pull --ff-only" { git pull --ff-only }
    } catch {
      Warn "Could not update the existing checkout (local changes or offline). Continuing with the version on disk."
    }
  } elseif (Test-Path -LiteralPath $InstallDir) {
    Fail "$InstallDir already exists but is not a Git repository. Choose another -InstallDir."
  } else {
    Run "git clone $RepoUrl $InstallDir" { git clone $RepoUrl $InstallDir }
    if ($script:DryRun) {
      Ok "Dry run stops here: the clone was not created."
      exit 0
    }
    Set-Location $InstallDir
  }
  # Re-enter from the checkout so the second half runs with the project as cwd.
  $Shell = if (Get-Command pwsh -ErrorAction SilentlyContinue) { "pwsh" } else { "powershell" }
  & $Shell -NoProfile -ExecutionPolicy Bypass -File (Join-Path (Get-Location) "install.ps1") `
    -InstallDir $InstallDir -Port $Port -NoStart:$NoStart -Cli:$Cli -DryRun:$DryRun
  exit $LASTEXITCODE
}

Step "Checking Python 3.10+"
function Find-Python {
  $Candidate = Get-Command python -ErrorAction SilentlyContinue
  if (-not $Candidate) { $Candidate = Get-Command py -ErrorAction SilentlyContinue }
  if (-not $Candidate) { return $null }
  & $Candidate.Source -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)"
  if ($LASTEXITCODE -eq 0) { return $Candidate }
  return $null
}

$Python = Find-Python
if (-not $Python) {
  if (Get-Command winget -ErrorAction SilentlyContinue) {
    Run "winget install Python.Python.3.12" { winget install Python.Python.3.12 --accept-package-agreements --accept-source-agreements }
    $Python = Find-Python
  }
}
if (-not $Python) {
  if ($script:DryRun) {
    Ok "Python 3.10+ would be installed"
  } else {
    Fail "Python 3.10+ is missing. Install Python 3.12 and run this script again."
  }
} else {
  Ok (& $Python.Source -c "import sys; print(sys.version.split()[0])")
}

# Disk space: ~4 GB for product/dependencies/PWA build. Model downloads do NOT
# happen here (the engine is chosen in the app) -> warning, no abort.
Step "Checking disk space"
$FreeGB = Get-FreeSpaceGB
if ($FreeGB -ge 0 -and $FreeGB -lt 4) {
  Warn "Less than ~4 GB free disk ($FreeGB GB). The installation is attempted anyway."
} else {
  Ok "Disk space OK"
}

# AI engine (info step, never blocking). Mandate 2026-08-21: Ollama is NOT installed
# and NO models are pulled. This step only checks whether Ollama is ready locally and
# shows a hint; the engine is chosen in the app (local Ollama, remote Ollama or an
# OpenAI-compatible endpoint).
Step "Check AI engine (info)"
$Ollama = Get-Command ollama -ErrorAction SilentlyContinue
$OllamaServiceOk = $false
if ($Ollama) {
  try {
    Invoke-RestMethod "$OllamaUrl/api/tags" -TimeoutSec 3 | Out-Null
    $OllamaServiceOk = $true
  } catch { }
}
if ($Ollama -and $OllamaServiceOk) {
  Ok "Ollama detected - its models are available for selection in the app."
} else {
  Warn "No Ollama detected - that is OK: Ephe does not install an AI of its own."
  Info "After the start you choose your engine in the app (local Ollama or an external endpoint such as DGX)."
}

Step "Setting up the local Python environment"
if ($script:DryRun) {
  Info "DRY-RUN: python -m venv .venv"
  Info "DRY-RUN: pip install --upgrade pip"
  if ($Cli) { Info 'DRY-RUN: pip install -e ".[tui]"' } else { Info 'DRY-RUN: pip install -e ".[gui,voice]"' }
} else {
  if (-not (Test-Path -LiteralPath ".venv")) {
    & $Python.Source -m venv .venv
    if ($LASTEXITCODE -ne 0) { Fail "Creating the virtual environment failed." }
  }
  # An existing `.venv` may be a `uv venv`: no pip module and no Scripts\pip.exe.
  # Seed pip behind a probe (install.sh carries the same guard) so the installs
  # below cannot die on `No module named pip`, and call pip as a module everywhere:
  # a seeded env answers on `python -m pip` even when it never got a pip.exe script.
  & ".\.venv\Scripts\python.exe" -m pip --version *> $null
  if ($LASTEXITCODE -ne 0) {
    Run "python -m ensurepip --upgrade" { & ".\.venv\Scripts\python.exe" -m ensurepip --upgrade }
  }
  Run "pip install --upgrade pip" { & ".\.venv\Scripts\python.exe" -m pip install --upgrade pip }
  if ($Cli) {
    Info "CLI mode: installing minimal dependencies (tui) only"
    Run 'pip install -e ".[tui]"' { & ".\.venv\Scripts\python.exe" -m pip install -e ".[tui]" }
  } else {
    Run 'pip install -e ".[gui,voice]"' { & ".\.venv\Scripts\python.exe" -m pip install -e ".[gui,voice]" }
  }
}
Ok "Dependencies installed"

# PWA build (desktop mode). The server serves the web app from app/dist, a build
# artifact that is git-ignored and therefore missing from a fresh clone. In desktop
# mode the frontend is built here so http://127.0.0.1:<Port>/ loads directly. CLI mode
# (TUI) needs no frontend -> the build is skipped (faster).
if (-not $Cli) {
  Step "Building the PWA (web app)"
  if ($script:DryRun) {
    Info "DRY-RUN: npm install --no-package-lock"
    Info "DRY-RUN: npm run build"
    Ok "PWA built -> app/dist"
  } else {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
      Fail "npm is missing - Node.js is required for the PWA build. Install Node.js (https://nodejs.org) and run the installer again."
    }
    Push-Location (Join-Path $PSScriptRoot "app")
    try {
      # `npm install --no-package-lock`, not `npm ci`: a fresh clone has no
      # package-lock.json and `npm ci` refuses that state with EUSAGE. Bare
      # `npm install` would write app/package-lock.json, the second lockfile that
      # tests/test_r46_pnpm_single_source.py forbids.
      Info "Building with npm (no package-lock.json is written)"
      Run "npm install --no-package-lock" { npm install --no-package-lock }
      Run "npm run build" { npm run build }
      if (-not (Test-Path -LiteralPath "dist/index.html")) {
        Fail "PWA build failed: dist/index.html does not exist."
      }
      Ok "PWA built -> app/dist"
    } finally {
      Pop-Location
    }
  }
} else {
  Info "CLI mode: the PWA build is skipped (the TUI needs no frontend)"
}

Step "Creating the local data folders"
$DataDirs = @("$HOME\.ephe\memory", "$HOME\.ephe\skills", "$HOME\.ephe\sessions\audio", "$HOME\.ephe\sessions\images")
if ($script:DryRun) {
  Info "DRY-RUN: New-Item -ItemType Directory -Force -Path $($DataDirs -join ', ')"
} else {
  New-Item -ItemType Directory -Force -Path $DataDirs | Out-Null
}
Ok "$HOME\.ephe ready"

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Project: $PWD"
Write-Host ""
# The `ephe` console script lands in `.venv\Scripts` and nothing here edits a
# PowerShell profile, so a bare `ephe` command in a NEW window answers "not
# recognized" - the same gap the Unix installer closes. Print the activation
# line first and the commands after it, matching install.sh's closing block.
Write-Host "The 'ephe' command is not on PATH yet - activate the environment first:"
Write-Host "  .\\.venv\\Scripts\\Activate.ps1"
Write-Host ""
Write-Host "Then, in that same shell:"
Write-Host "  ephe configure    # choose the engine once (saved to ~/.ephe/engine.json)"
Write-Host "  ephe doctor       # check Ollama, model and server state"
if ($Cli) {
  Write-Host "  ephe tui          # start the terminal UI"
} else {
  Write-Host "  ephe start --open # start the local app, then open http://127.0.0.1:$Port"
}
Write-Host ""

if (-not $NoStart -and -not $script:DryRun) {
  if ($Cli) {
    & ".\.venv\Scripts\ephe.exe" tui
  } else {
    & ".\.venv\Scripts\ephe.exe" start --port $Port --open
  }
}
