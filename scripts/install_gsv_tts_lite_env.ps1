param(
    [ValidateSet("CPU", "CU121", "CU126")]
    [string]$Device = "CPU",
    [string]$Python = ""
)

$ErrorActionPreference = "Stop"
$Root = "D:\AIhumannew"
$EnvDir = Join-Path $Root ".venvs\gsv-tts-lite"
$EnvFile = Join-Path $Root "backend\.env"
$Wheelhouse = Join-Path $Root "wheelhouse"

function Invoke-Step {
    param(
        [string]$Exe,
        [string[]]$CommandArgs
    )
    & $Exe @CommandArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $Exe $($CommandArgs -join ' ')"
    }
}

function Select-Python {
    param([string]$Requested)
    $candidates = @()
    if ($Requested) {
        $candidates += $Requested
    }
    $bundled = Join-Path $env:USERPROFILE ".cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
    $candidates += $bundled
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) {
        $candidates += $pythonCommand.Source
    }
    foreach ($candidate in $candidates) {
        if (-not $candidate -or -not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            continue
        }
        $versionText = & $candidate -c "import sys; print('{}.{}'.format(sys.version_info[0], sys.version_info[1])); sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) {
            Write-Host "Using Python $versionText at $candidate" -ForegroundColor Cyan
            return $candidate
        }
    }
    throw "Python 3.10+ is required. Pass -Python C:\Path\To\python.exe."
}

function Find-LocalTorchWheel {
    param(
        [string]$Package,
        [string]$DeviceTag
    )
    if (-not (Test-Path -LiteralPath $Wheelhouse -PathType Container)) {
        return $null
    }
    $pattern = "$Package-*+$DeviceTag-cp*-win_amd64.whl"
    $wheel = Get-ChildItem -LiteralPath $Wheelhouse -Filter $pattern -File -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    return $wheel
}

function Install-TorchPackages {
    param(
        [string]$DeviceName
    )
    if ($DeviceName -eq "CPU") {
        $deviceTag = "cpu"
        $indexUrl = "https://download.pytorch.org/whl/cpu"
    } elseif ($DeviceName -eq "CU121") {
        $deviceTag = "cu121"
        $indexUrl = "https://download.pytorch.org/whl/cu121"
    } else {
        $deviceTag = "cu126"
        $indexUrl = "https://download.pytorch.org/whl/cu126"
    }

    $torchWheel = Find-LocalTorchWheel -Package "torch" -DeviceTag $deviceTag
    $audioWheel = Find-LocalTorchWheel -Package "torchaudio" -DeviceTag $deviceTag
    if ($torchWheel -and $audioWheel) {
        Write-Host "Installing PyTorch from local wheelhouse: $($torchWheel.Name), $($audioWheel.Name)" -ForegroundColor Cyan
        Invoke-Step -Exe $venvPython -CommandArgs @(
            "-m", "pip", "install", "--force-reinstall",
            $torchWheel.FullName,
            $audioWheel.FullName
        )
        return
    }

    if ($DeviceName -ne "CPU") {
        Write-Host "Local wheelhouse missing CUDA wheels. Expected files like torch-*+$deviceTag-cp*-win_amd64.whl and torchaudio-*+$deviceTag-cp*-win_amd64.whl under $Wheelhouse." -ForegroundColor Yellow
        Write-Host "CU126 examples: torch-*+cu126-cp*-win_amd64.whl, torchaudio-*+cu126-cp*-win_amd64.whl" -ForegroundColor Yellow
    }
    Invoke-Step -Exe $venvPython -CommandArgs @(
        "-m", "pip", "install", "--force-reinstall",
        "torch", "torchaudio",
        "--index-url", $indexUrl
    )
}

$Python = Select-Python -Requested $Python

if (-not (Test-Path -LiteralPath (Join-Path $EnvDir "Scripts\python.exe") -PathType Leaf)) {
    Invoke-Step -Exe $Python -CommandArgs @("-m", "venv", $EnvDir)
} else {
    $existingVersion = & (Join-Path $EnvDir "Scripts\python.exe") -c "import sys; print('{}.{}'.format(sys.version_info[0], sys.version_info[1])); sys.exit(0 if sys.version_info >= (3, 10) else 1)" 2>$null
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Existing venv uses Python $existingVersion; recreating with Python 3.10+." -ForegroundColor Yellow
        Invoke-Step -Exe $Python -CommandArgs @("-m", "venv", "--clear", $EnvDir)
    }
}

$venvPython = Join-Path $EnvDir "Scripts\python.exe"
Invoke-Step -Exe $venvPython -CommandArgs @("-m", "pip", "install", "--upgrade", "pip")

Install-TorchPackages -DeviceName $Device

Invoke-Step -Exe $venvPython -CommandArgs @("-m", "pip", "install", "fastapi", "uvicorn", "pydantic", "gsv-tts-lite==0.4.5")

$gsvDevice = if ($Device -eq "CPU") { "" } else { "cuda" }
$updateScript = "from pathlib import Path; p=Path(r'$EnvFile'); updates={'GSV_TTS_LITE_PYTHON':r'$venvPython','GPT_SOVITS_PYTHON':r'$venvPython','GSV_TTS_LITE_API_URL':'http://127.0.0.1:9880','GSV_TTS_LITE_DEVICE':r'$gsvDevice'}; lines=p.read_text(encoding='utf-8').splitlines() if p.exists() else []; seen=set(); out=[]`nfor line in lines:`n    key=line.split('=',1)[0].strip() if '=' in line else ''`n    if key in updates:`n        if updates[key]: out.append(key+'='+updates[key])`n        seen.add(key)`n    else:`n        out.append(line)`nfor key,value in updates.items():`n    if key not in seen and value:`n        out.append(key+'='+value)`np.write_text('\n'.join(out)+'\n', encoding='utf-8')"
Invoke-Step -Exe $venvPython -CommandArgs @("-c", $updateScript)

Write-Host "GSV-TTS-Lite env ready: $venvPython" -ForegroundColor Green
Write-Host "GSV_TTS_LITE_PYTHON has been written to $EnvFile" -ForegroundColor Green
