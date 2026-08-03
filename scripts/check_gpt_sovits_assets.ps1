param(
    [string]$Repo = "D:\AIhumannew\third_party\GPT-SoVITS"
)

$pretrained = Join-Path $Repo "GPT_SoVITS\pretrained_models"
$checks = @(
    @{ Name = "api_v2.py"; Path = Join-Path $Repo "api_v2.py"; Type = "file" },
    @{ Name = "tts_infer.yaml"; Path = Join-Path $Repo "GPT_SoVITS\configs\tts_infer.yaml"; Type = "file" },
    @{ Name = "Chinese RoBERTa"; Path = Join-Path $pretrained "chinese-roberta-wwm-ext-large"; Type = "dir" },
    @{ Name = "Chinese HuBERT"; Path = Join-Path $pretrained "chinese-hubert-base"; Type = "dir" },
    @{ Name = "GPT v2 checkpoint"; Path = Join-Path $pretrained "gsv-v2final-pretrained\s1bert25hz-5kh-longer-epoch=12-step=369668.ckpt"; Type = "file" },
    @{ Name = "SoVITS v2 checkpoint"; Path = Join-Path $pretrained "gsv-v2final-pretrained\s2G2333k.pth"; Type = "file" },
    @{ Name = "G2PWModel"; Path = Join-Path $Repo "GPT_SoVITS\text\G2PWModel"; Type = "dir" }
)

$ok = $true
$missing = @()
foreach ($item in $checks) {
    $exists = if ($item.Type -eq "dir") { Test-Path -LiteralPath $item.Path -PathType Container } else { Test-Path -LiteralPath $item.Path -PathType Leaf }
    if (-not $exists) {
        $ok = $false
        $missing += $item
    }
    [PSCustomObject]@{
        Name = $item.Name
        Exists = $exists
        Path = $item.Path
    }
}

if ($ok) {
    Write-Host "GPT-SoVITS assets look ready." -ForegroundColor Green
    exit 0
}

Write-Host "GPT-SoVITS assets are incomplete. See docs\gpt_sovits_setup.md." -ForegroundColor Yellow
Write-Host "Missing:" -ForegroundColor Yellow
foreach ($item in $missing) {
    Write-Host "  - $($item.Name): $($item.Path)" -ForegroundColor Yellow
}
exit 1
