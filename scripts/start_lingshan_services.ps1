$ErrorActionPreference = "Stop"

$root = "D:\AIhumannew"
$python = "C:\Users\Administrator\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
$logs = Join-Path $root "logs"

New-Item -ItemType Directory -Force -Path $logs | Out-Null

$env:FUNASR_STREAMING_MODEL_DIR = Join-Path $root "models\FunASR\paraformer-zh-streaming"
$env:FUNASR_VAD_MODEL_DIR = Join-Path $root "models\FunASR\fsmn-vad"
$env:FUNASR_PUNC_MODEL_DIR = Join-Path $root "models\FunASR\ct-punc"
$env:FUNASR_DEVICE = "cuda:0"
$env:REALTIME_SILENCE_END_MS = "800"
$env:REALTIME_MIN_SPEECH_MS = "500"
$env:REALTIME_MAX_LISTEN_MS = "15000"

function Stop-PortListener {
    param([int]$Port)
    $pids = netstat -ano |
        Select-String ":$Port" |
        ForEach-Object { ($_ -split "\s+")[-1] } |
        Where-Object { $_ -match "^\d+$" -and $_ -ne "0" } |
        Sort-Object -Unique
    foreach ($procId in $pids) {
        taskkill /PID $procId /F 2>$null | Out-Null
    }
}

function Start-PythonService {
    param(
        [string]$Name,
        [string]$Script,
        [string]$Stdout,
        [string]$Stderr
    )
    $psi = [System.Diagnostics.ProcessStartInfo]::new()
    $psi.FileName = $python
    $psi.Arguments = "`"$Script`""
    $psi.WorkingDirectory = Join-Path $root "backend"
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $false
    $psi.RedirectStandardError = $false
    $psi.Environment["FUNASR_STREAMING_MODEL_DIR"] = $env:FUNASR_STREAMING_MODEL_DIR
    $psi.Environment["FUNASR_VAD_MODEL_DIR"] = $env:FUNASR_VAD_MODEL_DIR
    $psi.Environment["FUNASR_PUNC_MODEL_DIR"] = $env:FUNASR_PUNC_MODEL_DIR
    $psi.Environment["FUNASR_DEVICE"] = $env:FUNASR_DEVICE
    $psi.Environment["REALTIME_SILENCE_END_MS"] = $env:REALTIME_SILENCE_END_MS
    $psi.Environment["REALTIME_MIN_SPEECH_MS"] = $env:REALTIME_MIN_SPEECH_MS
    $psi.Environment["REALTIME_MAX_LISTEN_MS"] = $env:REALTIME_MAX_LISTEN_MS
    $process = [System.Diagnostics.Process]::Start($psi)
    Write-Output "$Name PID=$($process.Id)"
}

Stop-PortListener -Port 8000
Stop-PortListener -Port 8010
Start-Sleep -Seconds 2

Start-PythonService -Name "Flask 8000" -Script (Join-Path $root "backend\main.py") -Stdout (Join-Path $logs "backend_stdout.log") -Stderr (Join-Path $logs "backend_stderr.log")
Start-PythonService -Name "Realtime 8010" -Script (Join-Path $root "backend\realtime_server.py") -Stdout (Join-Path $logs "realtime_stdout.log") -Stderr (Join-Path $logs "realtime_stderr.log")
