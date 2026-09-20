<#
.SYNOPSIS
    기준선(scripts\eval\run_eval.py)을 하루 한 번 저절로 돌린다 — **추세는 표본이 쌓여야 보인다.**

    .\nightly.ps1 -Register            # 작업 스케줄러에 매일 03:00 (한 번, 현재 사용자로)
    .\nightly.ps1 -Unregister
    .\nightly.ps1 -Status
    .\nightly.ps1                      # 지금 한 번 (작업이 부르는 것과 같은 길)

.DESCRIPTION
    다섯 번을 손으로 돌리는 동안 매번 25분씩 기다리고 json 을 열어 견줬다(2026-09-20).
    세션마다 값이 들어 한 번의 통과 수로는 「나아졌다」 를 말할 수 없는데, 표본이 다섯
    점뿐이었다. 이 작업이 `results\trend.csv` 에 하루 한 줄씩 쌓고, 사람은 그 파일 하나만
    본다.

    ## 토큰

    `scripts\eval\.pat` 에 개인 토큰(mnx_pat_…)을 한 줄로 둔다. **.gitignore 에 있다** —
    화면 → 내 계정 → 토큰에서 기준선용 계정으로 발급한다. 없으면 이 스크립트는 로그 한
    줄 남기고 그만둔다. 환경 변수 MATNEXUS_PAT 이 있으면 그것이 먼저다.

    ## 백엔드

    개발 백엔드(8011)가 떠 있어야 한다. 안 떠 있으면 **띄우지 않고** 로그 한 줄로 그만둔다 —
    야간에 백엔드를 띄우는 것은 이 작업의 일이 아니다(그 사이 마이그레이션이 걸려 있을
    수 있다).

    ## 꺾이면

    직전 줄보다 통과 수가 -3 이상 떨어지면 로그에 「꺾임」 을 크게 남긴다. 알림 채널이
    아직 없으니 그것이 전부다 — 알림이 생기면 그 자리에 잇는다.

    ## 5.1

    Windows PowerShell 5.1 을 전제한다. 이 파일은 UTF-8 BOM 으로 저장해야 한다 — BOM 이
    없으면 5.1 이 CP949 로 읽어 한글이 깨지고 구문 오류가 난다(AGENTS.md).
#>
param(
    [string]$ApiBase = 'http://127.0.0.1:8011/api',
    [string]$TaskName = 'MatNexus-Eval-Nightly',
    [string]$At = '03:00',
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Status
)

$ErrorActionPreference = 'Stop'

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Resolve-Path (Join-Path $here '..\..')
$python = Join-Path $repo 'backend\.venv\Scripts\python.exe'
$results = Join-Path $here 'results'
$logFile = Join-Path $results 'nightly.log'
$patFile = Join-Path $here '.pat'
$trend = Join-Path $results 'trend.csv'

function Write-Log([string]$Message) {
    if (-not (Test-Path $results)) { New-Item -ItemType Directory -Path $results | Out-Null }
    $line = "{0:yyyy-MM-dd HH:mm:ss} {1}" -f (Get-Date), $Message
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

if ($Register) {
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
    $me = Join-Path $here 'nightly.ps1'
    $argument = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$me`" -ApiBase `"$ApiBase`""
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument -WorkingDirectory $here
    $trigger = New-ScheduledTaskTrigger -Daily -At $At
    # 현재 사용자로 돈다 — claude CLI 의 로그인과 PATH 가 그 사용자 것이다. SYSTEM 으로 돌리면
    # claude 를 못 찾는다.
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Hours 2)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings `
        -Description "MatNexus 기준선 — 매일 $At 에 scripts\eval\run_eval.py 를 돌려 results\trend.csv 에 한 줄 쌓는다." | Out-Null
    Write-Log "'$TaskName' 등록 — 매일 $At, 백엔드 $ApiBase (스크립트: $me)"
    exit 0
}

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Log "'$TaskName' 해제"
    } else {
        Write-Host "'$TaskName' 은 등록돼 있지 않습니다."
    }
    exit 0
}

if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if (-not $task) { Write-Host "'$TaskName' 은 등록돼 있지 않습니다."; exit 1 }
    $info = Get-ScheduledTaskInfo -TaskName $TaskName
    Write-Host ("작업: {0} · 상태 {1} · 마지막 {2} ({3}) · 다음 {4}" -f $TaskName, $task.State, $info.LastRunTime, $info.LastTaskResult, $info.NextRunTime)
    if (Test-Path $trend) {
        Write-Host "--- trend.csv 마지막 5줄 ---"
        Get-Content $trend -Tail 5
    }
    exit 0
}

# ── 지금 한 번 ────────────────────────────────────────────────────────────

$token = $env:MATNEXUS_PAT
if (-not $token -and (Test-Path $patFile)) {
    $token = (Get-Content $patFile -TotalCount 1).Trim()
}
if (-not $token) {
    Write-Log "토큰이 없다 — $patFile 에 mnx_pat_… 한 줄을 두거나 MATNEXUS_PAT 을 주세요. 그만둡니다."
    exit 2
}
if (-not (Test-Path $python)) {
    Write-Log "백엔드 가상환경이 없다: $python. 그만둡니다."
    exit 2
}

try {
    $health = Invoke-WebRequest -Uri ($ApiBase.TrimEnd('/') + '/health') -UseBasicParsing -TimeoutSec 10
    if ($health.StatusCode -ne 200) { throw "health $($health.StatusCode)" }
} catch {
    Write-Log "백엔드($ApiBase)가 답이 없다 — 띄우지 않고 그만둡니다: $_"
    exit 3
}

$before = $null
if (Test-Path $trend) {
    $last = Get-Content $trend -Tail 1
    if ($last -and -not $last.StartsWith('stamp')) { $before = [int]($last.Split(',')[3]) }
}

Write-Log "기준선 시작 ($ApiBase)"
$env:MATNEXUS_PAT = $token
$env:MATNEXUS_API_BASE = $ApiBase
$env:PYTHONIOENCODING = 'utf-8'
Push-Location $here
try {
    # 5.1 은 네이티브 stderr 한 줄을 종료성 오류로 바꾼다 — 출력은 파일로 받고 종료 코드만 본다.
    $out = Join-Path $results 'nightly-last.log'
    $proc = Start-Process -FilePath $python -ArgumentList 'run_eval.py' -NoNewWindow -Wait -PassThru `
        -RedirectStandardOutput $out -RedirectStandardError (Join-Path $results 'nightly-last.err')
    if ($proc.ExitCode -ne 0) {
        Write-Log "run_eval.py 종료 코드 $($proc.ExitCode) — $out 을 보세요."
        exit $proc.ExitCode
    }
} finally {
    Pop-Location
}

$row = Get-Content $trend -Tail 1
$cells = $row.Split(',')
$passed = [int]$cells[3]; $n = [int]$cells[2]
$summary = "기준선 끝 — 통과 $passed/$n · 호출 $($cells[4]) · 빈손 $($cells[6]) · 오류 $($cells[8])"
Write-Log $summary
if ($null -ne $before -and ($before - $passed) -ge 3) {
    Write-Log "!!! 꺾임 — 직전 $before → $passed. results\latest.md 의 미달 줄을 보세요."
}
exit 0
