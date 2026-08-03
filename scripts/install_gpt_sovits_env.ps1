param(
    [ValidateSet("CU126", "CU128", "CPU")]
    [string]$Device = "CU126",
    [ValidateSet("ModelScope", "HF", "HF-Mirror")]
    [string]$Source = "ModelScope",
    [string]$EnvName = "GPTSoVits"
)

$ErrorActionPreference = "Stop"
$Root = "D:\AIhumannew"
$Repo = Join-Path $Root "third_party\GPT-SoVITS"
$EnvFile = Join-Path $Root "backend\.env"

if (-not (Get-Command conda -ErrorAction SilentlyContinue)) {
    throw "conda not found. Please install Anaconda/Miniconda and ensure conda is available in PATH."
}

if (-not (Test-Path -LiteralPath (Join-Path $Repo "install.ps1") -PathType Leaf)) {
    throw "GPT-SoVITS repo is missing. Expected: $Repo"
}

$envList = conda env list | Out-String
if ($envList -notmatch "(^|\s)$EnvName(\s|$)") {
    conda create -n $EnvName python=3.10 -y
}

conda run -n $EnvName python -m pip install --upgrade pip
Push-Location $Repo
try {
    conda run -n $EnvName powershell -ExecutionPolicy Bypass -File install.ps1 -Device $Device -Source $Source
} finally {
    Pop-Location
}

$python = (conda run -n $EnvName python -c "import sys; print(sys.executable)").Trim()

python -c "from pathlib import Path; p=Path(r'$EnvFile'); key='GPT_SOVITS_PYTHON'; value=r'$python'; lines=p.read_text(encoding='utf-8').splitlines() if p.exists() else []; found=False; out=[]; [out.append((key+'='+value) if line.startswith(key+'=') else line) for line in lines]; found=any(line.startswith(key+'=') for line in lines); out.append(key+'='+value) if not found else None; p.write_text('\n'.join(out)+'\n', encoding='utf-8')"

Write-Host "GPT-SoVITS env ready: $python" -ForegroundColor Green
Write-Host "GPT_SOVITS_PYTHON has been written to $EnvFile" -ForegroundColor Green
