<#
감시 — `/api/health` 가 답하지 않으면 서비스를 다시 띄운다.

    .\watchdog.ps1 -AppPath 'C:\Server\MatNexus' -Register     # 작업 스케줄러에 1분마다 (한 번)
    .\watchdog.ps1 -AppPath 'C:\Server\MatNexus'               # 한 번 검사 (작업이 부르는 것)
    .\watchdog.ps1 -AppPath 'C:\Server\MatNexus' -Status       # 최근 로그와 실패 횟수
    .\watchdog.ps1 -AppPath 'C:\Server\MatNexus' -Unregister

## 왜 필요한가 (2026-09-17)

서비스(NSSM)는 **프로세스가 사라지면** 되살린다. 그런데 실측(2026-09-10, 두 번)의
증상은 그것이 아니었다 — 사내망에서 DB 연결이 잠깐 끊긴 뒤 백엔드가 **떠 있는 채로
요청을 받지 않았다.** 프로세스는 살아 있으니 SCM 은 아무 일도 없는 줄 안다. 그동안
화면은 안 뜨고, AI(MCP)는 「자료가 없다」 로 답한다. 사람이 알아채고 재기동할 때까지다.

`/api/health` 는 그 뒤 DB 까지 찔러 보고 답하게 고쳤지만(v1.24x), **그것을 보는
사람이 없으면 소용없다.** 이 스크립트가 그 눈이다 — 1분마다 묻고, 잇달아 세 번
답이 없으면 `MatNexus` 서비스를 다시 띄운다.

## 무엇을 재시작으로 보고, 무엇을 안 보나

    200 ok                       정상. 실패 횟수를 지운다.
    503 degraded                 앱은 살아 있고 DB 에 못 닿는 것 — **재시작하지 않는다.**
                                 재시작해도 DB 는 안 돌아오고, 앱은 DB 가 돌아오면 스스로
                                 재연결한다(pool_pre_ping). 로그에만 남긴다.
    응답 없음 · 타임아웃 · 거절   앱이 멈췄거나 없다 — 실패 횟수 +1. 잇달아 -Threshold(3)
                                 번이면 재시작. 한 번의 실패로 재시작하지 않는 것은 배포
                                 중(deploy.ps1 이 서비스를 잠깐 멈춘다)에 끼어들지 않으려고다.

재시작은 **10분에 한 번**까지다 — 뜨자마자 또 죽는 것을 1분마다 되살리면 로그만
쌓이고 원인은 안 보인다. 그때는 `_data\logs\service-server.log` 의 첫 줄을 본다.

**서비스가 `Running` 일 때만 손댄다.** `Stopped` 면 누가 일부러 멈춘 것이다 — 배포
(deploy.ps1 · rollback.ps1 이 교체 동안 멈춘다)나 관리자. 그때 띄우면 교체 중인 폴더
위에서 앱이 뜬다. 프로세스가 *죽은* 것은 NSSM 이 이미 되살리므로 여기서 볼 일이 없다 —
이 스크립트의 몫은 오직 「떠 있는데(Running) 답이 없다」 다.

서비스로 등록돼 있지 않으면(창 방식 `run_server.ps1`) 재시작할 수 없다 — 로그에
그 사실을 남기고 만다. 그 방식은 사람이 창을 보고 있다는 전제다.

## 어디에 남나

    <AppPath>_data\logs\watchdog.log      한 줄씩. 정상일 때는 조용하다(회복될 때만 한 줄).
    <AppPath>_data\logs\watchdog.state    잇단 실패 횟수 · 마지막 재시작 시각

작업은 SYSTEM 으로 돈다(서비스를 다시 띄우려면 관리자여야 한다). -Register 는
관리자 PowerShell 에서.
#>

param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    # 비우면 backend\.env 의 PORT, 그것도 없으면 8010.
    [int]$Port = 0,
    [string]$ServiceName = 'MatNexus',
    [string]$TaskName = 'MatNexus-Watchdog',
    # 잇달아 이만큼 답이 없어야 재시작한다.
    [int]$Threshold = 3,
    [int]$TimeoutSec = 15,
    # 재시작 뒤 이 시간 안에는 다시 재시작하지 않는다(분).
    [int]$CooldownMinutes = 10,
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Status,
    # 재시작할 자리에서 로그만 남기고 실제로는 안 띄운다.
    [switch]$DryRun
)

$ErrorActionPreference = 'Stop'

if ($AppPath.StartsWith('-')) { throw "-AppPath 값이 '$AppPath' 입니다 — 대시를 두 번 쓰신 것 같습니다." }
$AppPath = $AppPath.TrimEnd('\')
$logDir = Join-Path ($AppPath + '_data') 'logs'
$logFile = Join-Path $logDir 'watchdog.log'
$stateFile = Join-Path $logDir 'watchdog.state'
$envFile = Join-Path $AppPath 'backend\.env'

function Read-EnvValue([string]$name) {
    if (-not (Test-Path $envFile)) { return $null }
    $line = Select-String -Path $envFile -Pattern ("^\s*" + $name + "\s*=\s*(.+)$") | Select-Object -First 1
    if (-not $line) { return $null }
    return $line.Matches[0].Groups[1].Value.Trim().Trim('"').Trim("'")
}

if ($Port -le 0) {
    $fromEnv = Read-EnvValue 'PORT'
    $Port = if ($fromEnv) { [int]$fromEnv } else { 8010 }
}
$healthUrl = "http://127.0.0.1:$Port/api/health"

function Write-Log([string]$m) {
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
    # 1 MB 를 넘으면 한 판 물린다 — 감시 로그가 디스크를 먹으면 그것이 새 장애다.
    if ((Test-Path $logFile) -and ((Get-Item $logFile).Length -gt 1MB)) {
        Move-Item -Force $logFile ($logFile + '.1')
    }
    $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $m"
    Add-Content -Path $logFile -Value $line -Encoding UTF8
    Write-Host $line
}

function Read-State {
    $state = @{ failures = 0; last_restart = ''; degraded = 0 }
    if (Test-Path $stateFile) {
        foreach ($line in Get-Content $stateFile) {
            $pair = $line -split '=', 2
            if ($pair.Count -eq 2) { $state[$pair[0].Trim()] = $pair[1].Trim() }
        }
        $state.failures = [int]$state.failures
        $state.degraded = [int]$state.degraded
    }
    return $state
}

function Write-State([hashtable]$state) {
    if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Force $logDir | Out-Null }
    Set-Content -Path $stateFile -Encoding UTF8 -Value @(
        "failures=$($state.failures)",
        "last_restart=$($state.last_restart)",
        "degraded=$($state.degraded)"
    )
}

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw '작업을 등록·해제하려면 관리자 PowerShell 에서 실행해야 합니다.'
    }
}

# --- 등록 · 해제 · 상태 --------------------------------------------------------
if ($Register) {
    Assert-Admin
    # 등록된 작업은 _tools 의 복사본을 부른다 — 패키지 폴더는 배포마다 바뀌지만 _tools 는 남는다
    # (service.ps1 이 nssm 을 두는 곳과 같은 판단).
    $toolsPath = $AppPath + '_tools'
    if (-not (Test-Path $toolsPath)) { New-Item -ItemType Directory -Force $toolsPath | Out-Null }
    $installed = Join-Path $toolsPath 'watchdog.ps1'
    Copy-Item -Force $PSCommandPath $installed
    $existing = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    if ($existing) { Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false }
    $argument = "-NoProfile -NonInteractive -ExecutionPolicy Bypass -File `"$installed`" -AppPath `"$AppPath`" -Port $Port -ServiceName $ServiceName -Threshold $Threshold -TimeoutSec $TimeoutSec -CooldownMinutes $CooldownMinutes"
    $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argument
    # 1분마다, 끝없이. 시작 시 트리거를 따로 두지 않는다 — 반복 트리거가 부팅 뒤 첫 분부터 돈다.
    # RepetitionDuration 을 안 주면 5.1 이 등록을 거절한다 — 10년이면 「끝없이」 다.
    $trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date -RepetitionInterval (New-TimeSpan -Minutes 1) -RepetitionDuration (New-TimeSpan -Days 3650)
    $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
    $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
        -StartWhenAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
    Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
        -Principal $principal -Settings $settings `
        -Description "MatNexus 감시 — $healthUrl 이 잇달아 $Threshold 번 답이 없으면 $ServiceName 서비스를 다시 띄운다." | Out-Null
    Write-Log "'$TaskName' 등록 — 1분마다 $healthUrl 을 봅니다 (스크립트: $installed)"
    exit 0
}

if ($Unregister) {
    Assert-Admin
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Log "'$TaskName' 해제"
    } else {
        Write-Host "'$TaskName' 작업이 없습니다."
    }
    exit 0
}

if ($Status) {
    $task = Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue
    Write-Host ("  작업:   " + $(if ($task) { "$TaskName ($($task.State))" } else { "$TaskName 등록 안 됨 — -Register" }))
    $state = Read-State
    Write-Host "  대상:   $healthUrl"
    Write-Host "  잇단 실패: $($state.failures) / $Threshold   DB 못 닿음: $(if ($state.degraded) { '예' } else { '아니오' })   마지막 재시작: $(if ($state.last_restart) { $state.last_restart } else { '없음' })"
    if (Test-Path $logFile) {
        Write-Host "  로그($logFile) 마지막 10줄:"
        Get-Content $logFile -Tail 10 | ForEach-Object { Write-Host "    $_" }
    } else {
        Write-Host '  로그 없음 — 아직 한 번도 안 돌았거나 늘 정상이었습니다.'
    }
    exit 0
}

# --- 한 번 검사 -----------------------------------------------------------------
$state = Read-State
$verdict = 'down'
$detail = ''
try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $healthUrl -TimeoutSec $TimeoutSec
    $verdict = 'ok'
    $detail = $response.Content
} catch {
    $ex = $_.Exception
    $http = $null
    if ($ex.Response) {
        try { $http = [int]$ex.Response.StatusCode } catch { $http = $null }
    }
    if ($http -eq 503) {
        # 앱이 답했다 — DB 쪽 문제. 본문에 이유가 있다.
        $verdict = 'degraded'
        $detail = if ($_.ErrorDetails -and $_.ErrorDetails.Message) { $_.ErrorDetails.Message } else { '(본문 없음)' }
    } elseif ($http) {
        # 200 도 503 도 아닌 HTTP 응답 — 앱은 살아 있다고 본다(프록시가 낸 것일 수도 있다).
        $verdict = 'ok'
        $detail = "HTTP $http"
    } else {
        $detail = $ex.Message
    }
}

switch ($verdict) {
    'ok' {
        if ($state.failures -gt 0) { Write-Log "회복 — $($state.failures)번 답이 없다가 다시 답합니다: $detail" }
        if ($state.degraded -ne 0) { Write-Log "DB 회복 — 다시 ok 입니다: $detail" }
        if ($state.failures -gt 0 -or $state.degraded -ne 0) {
            $state.failures = 0
            $state.degraded = 0
            Write-State $state
        }
        exit 0
    }
    'degraded' {
        # 재시작하지 않는다 — 앱은 살아 있다. 실패 횟수도 늘리지 않는다. 첫 번만 적는다.
        if ($state.degraded -eq 0) {
            Write-Log "DB 에 못 닿음(503) — 재시작하지 않습니다. PostgreSQL 서비스·네트워크를 보세요: $detail"
        }
        if ($state.failures -gt 0 -or $state.degraded -eq 0) {
            $state.failures = 0
            $state.degraded = 1
            Write-State $state
        }
        exit 0
    }
}

# 응답 없음
$state.failures = $state.failures + 1
Write-Log "답 없음 ($($state.failures)/$Threshold): $detail"
if ($state.failures -lt $Threshold) { Write-State $state; exit 0 }

$service = Get-Service -Name $ServiceName -ErrorAction SilentlyContinue
if (-not $service) {
    Write-Log "잇달아 $Threshold 번 답이 없지만 '$ServiceName' 서비스가 없습니다 — 창 방식이면 사람이 다시 띄워야 합니다."
    $state.failures = 0
    Write-State $state
    exit 0
}

if ($service.Status -ne 'Running') {
    # 멈춘 것은 누가 멈춘 것이다(배포 · 관리자). 죽은 것은 NSSM 이 되살린다. 여기서 띄우면
    # 교체 중인 폴더 위에서 앱이 뜬다 — 손대지 않는다.
    Write-Log "잇달아 $Threshold 번 답이 없지만 '$ServiceName' 이 $($service.Status) 상태입니다 — 배포 중이거나 일부러 멈춘 것이라 손대지 않습니다."
    $state.failures = 0
    Write-State $state
    exit 0
}

if ($state.last_restart) {
    $since = (Get-Date) - [datetime]::ParseExact($state.last_restart, 'yyyy-MM-dd HH:mm:ss', $null)
    if ($since.TotalMinutes -lt $CooldownMinutes) {
        Write-Log ("잇달아 $Threshold 번 답이 없지만 {0:N0}분 전에 재시작했습니다 — {1}분 안에는 다시 하지 않습니다. service-server.log 첫 줄을 보세요." -f $since.TotalMinutes, $CooldownMinutes)
        exit 0
    }
}

$state.failures = 0
$state.last_restart = (Get-Date).ToString('yyyy-MM-dd HH:mm:ss')
Write-State $state
if ($DryRun) {
    Write-Log "[dry-run] '$ServiceName' 을 다시 띄웠을 자리입니다 (상태: $($service.Status))."
    exit 0
}
Write-Log "'$ServiceName' 을 다시 띄웁니다 (상태: $($service.Status))."
try {
    Stop-Service -Name $ServiceName -Force -ErrorAction Stop
    Start-Service -Name $ServiceName -ErrorAction Stop
    Write-Log "'$ServiceName' 시작 — 다음 검사에서 답하는지 봅니다."
} catch {
    Write-Log "재시작 실패: $($_.Exception.Message)"
    exit 1
}
