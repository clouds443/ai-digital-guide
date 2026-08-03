param(
    [ValidateSet("ModelScope", "HF", "HF-Mirror")]
    [string]$Source = "ModelScope",
    [string]$Repo = "D:\AIhumannew\third_party\GPT-SoVITS",
    [string]$CacheDir = "D:\AIhumannew\models\downloads"
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path -LiteralPath $Repo -PathType Container)) {
    throw "GPT-SoVITS repo not found: $Repo"
}

if ($Source -eq "HF") {
    $pretrainedUrl = "https://huggingface.co/XXXXRT/GPT-SoVITS-Pretrained/resolve/main/pretrained_models.zip"
    $g2pwUrl = "https://huggingface.co/XXXXRT/GPT-SoVITS-Pretrained/resolve/main/G2PWModel.zip"
} elseif ($Source -eq "HF-Mirror") {
    $pretrainedUrl = "https://hf-mirror.com/XXXXRT/GPT-SoVITS-Pretrained/resolve/main/pretrained_models.zip"
    $g2pwUrl = "https://hf-mirror.com/XXXXRT/GPT-SoVITS-Pretrained/resolve/main/G2PWModel.zip"
} else {
    $pretrainedUrl = "https://www.modelscope.cn/models/XXXXRT/GPT-SoVITS-Pretrained/resolve/master/pretrained_models.zip"
    $g2pwUrl = "https://www.modelscope.cn/models/XXXXRT/GPT-SoVITS-Pretrained/resolve/master/G2PWModel.zip"
}

New-Item -ItemType Directory -Force -Path $CacheDir | Out-Null

function Download-IfMissing {
    param(
        [string]$Url,
        [string]$OutFile
    )
    if (Test-Path -LiteralPath $OutFile -PathType Leaf) {
        Write-Host "Exists: $OutFile" -ForegroundColor DarkGray
        return
    }
    Write-Host "Downloading: $Url" -ForegroundColor Cyan
    Invoke-WebRequest -Uri $Url -OutFile $OutFile
}

$pretrainedZip = Join-Path $CacheDir "pretrained_models.zip"
$g2pwZip = Join-Path $CacheDir "G2PWModel.zip"

Download-IfMissing -Url $pretrainedUrl -OutFile $pretrainedZip
Download-IfMissing -Url $g2pwUrl -OutFile $g2pwZip

Write-Host "Expanding pretrained models..." -ForegroundColor Cyan
Expand-Archive -LiteralPath $pretrainedZip -DestinationPath (Join-Path $Repo "GPT_SoVITS") -Force

Write-Host "Expanding G2PWModel..." -ForegroundColor Cyan
Expand-Archive -LiteralPath $g2pwZip -DestinationPath (Join-Path $Repo "GPT_SoVITS\text") -Force

Write-Host "Done. Verifying assets..." -ForegroundColor Cyan
powershell -ExecutionPolicy Bypass -File "D:\AIhumannew\scripts\check_gpt_sovits_assets.ps1" -Repo $Repo
