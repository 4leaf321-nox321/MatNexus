<#
Windows 서비스 등록 — 재부팅해도 서버와 워커가 저절로 뜬다.

    .\service.ps1 -AppPath 'C:\Server\MatNexus' -Action Install     # 한 번
    .\service.ps1 -AppPath 'C:\Server\MatNexus' -Action Status
    .\service.ps1 -AppPath 'C:\Server\MatNexus' -Action Restart
    .\service.ps1 -AppPath 'C:\Server\MatNexus' -Action Uninstall

## 왜 서비스인가 (2026-09-15)

`run_server.ps1`(D9, 콘솔 실행)은 창을 닫으면 서버가 멈추고 재부팅하면 사람이
다시 띄워야 했다. 작업 스케줄러(시작 시 트리거)는 「켜 주는 것」 이고, 프로세스가
멈춰 있기만 하면 못 알아챈다. 서비스는 「돌아가게 책임지는 것」 이다 — 프로세스가
사라지면 SCM 이 되살리고, `Stop-Service` 가 자식까지 정리한다.

## 무엇으로

NSSM(bin\nssm.exe, 2.24, 퍼블릭 도메인)이 python.exe 를 감싼다. 폐쇄망 반입 항목이
하나 늘지만(331 KB) 패키지에 동봉되므로 따로 받을 것은 없다. 등록할 때 nssm.exe 를
`<AppPath>_tools\` 로 **복사해 둔다** — 서비스의 실행 파일이 `<AppPath>` 안에 있으면
배포가 폴더를 통째로 바꿀 때 SCM 이 가리키는 파일이 사라졌다 나타나는 셈이다.
`_venvs`·`_data` 처럼 배포가 건드리지 않는 자리에 둔다.

## 등록되는 것

    MatNexus         backend\run.py          (API + 화면)
    MatNexusWorker   backend\run_worker.py   (작업 큐 — 파싱·처리·알림)
    MatNexusMcp      mcp_server\server.py    (AI 연결 — 다른 가상환경 `_venvs\mcp_server`)

MCP 는 창 방식(`run_mcp.ps1`)이 읽어 주던 `backend\.env` 의 PORT·MCP_PORT·MCP_HOST·
MCP_ALLOWED_HOSTS 를 `server.py` 가 직접 읽는다(환경변수가 비어 있을 때만) — 등록할 때
값을 박아 두면 .env 를 고쳐도 서비스는 옛 포트를 보기 때문이다. `-NoMcp` 로 뺀다.

둘 다 지연 자동 시작(부팅 뒤 PostgreSQL 이 먼저 뜰 시간을 준다), PostgreSQL 서비스가
있으면 그것에 의존을 걸고, 죽으면 10초 뒤 되살린다. **떠 있는데 멈춘 것**은 SCM 이
못 알아채므로 `watchdog.ps1` 을 작업 스케줄러에 함께 등록한다(1분마다 `/api/health`,
잇달아 세 번 답이 없으면 MatNexus 재시작 — 그 스크립트의 머리 참조). `-NoWatchdog` 로 뺀다. stdout/stderr 는
`<AppPath>_data\logs\service-*.log` 로 가고 10 MB 마다 돌린다 — 앱 로그(app.log)와는
별도다. 콘솔이 없으므로 `PYTHONUTF8=1` 을 준다(한글 배너가 cp949 로 깨지지 않게).

## deploy.ps1 과의 관계

deploy.ps1 은 이 두 서비스가 있으면 **먼저 멈추고, 끝나면 다시 띄운다.** 그래서
서비스로 등록한 뒤에는 배포 뒤에 창을 열 일이 없다. 워커도 새 코드로 다시 뜬다 —
옛 워커가 남아 새 작업 종류를 모르는 사고(2026-08-28)가 서비스에서는 안 난다.

관리자 PowerShell 에서 실행한다 — 서비스 등록은 관리자 권한이 필요하다.
#>

param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [ValidateSet('Install', 'Uninstall', 'Start', 'Stop', 'Restart', 'Status')]
    [string]$Action = 'Status',
    # 워커를 서비스로 안 두고 싶을 때(예: 워커를 다른 PC 에서 돌린다).
    [switch]$NoWorker,
    # MCP(AI 연결)를 서비스로 안 두고 싶을 때. 없어도 앱은 멀쩡히 돈다.
    [switch]$NoMcp,
    # PostgreSQL 서비스 이름. 비우면 'postgresql*' 로 찾는다. 'none' 이면 의존을 안 건다.
    [string]$DbService,
    # 감시 작업(watchdog.ps1)을 등록하지 않는다 — 다른 감시가 이미 있을 때.
    [switch]$NoWatchdog
)

$ErrorActionPreference = 'Stop'

function Assert-NotFlag([string]$value, [string]$name) {
    if ($value -and $value.StartsWith('-')) {
        throw "-$name 값이 '$value' 입니다 — 대시를 두 번 쓰신 것 같습니다. PowerShell 매개변수는 대시가 하나입니다: -$name '<값>'"
    }
}
Assert-NotFlag $AppPath 'AppPath'
Assert-NotFlag $DbService 'DbService'

function Write-Log([string]$m) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $m" }

# 네이티브 명령 — stderr 를 오류로 착각하지 않는다(5.1). 종료 코드로만 판정한다.
function Invoke-Native {
    param([Parameter(Mandatory = $true)][string]$FailureMessage, [Parameter(Mandatory = $true)][scriptblock]$Command)
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $Command
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "$FailureMessage (exit $code)" }
}

$AppPath = $AppPath.TrimEnd('\')
$toolsPath = $AppPath + '_tools'
$dataPath = $AppPath + '_data'
$venvPython = Join-Path ($AppPath + '_venvs') 'backend\Scripts\python.exe'
$mcpPython = Join-Path ($AppPath + '_venvs') 'mcp_server\Scripts\python.exe'
$backend = Join-Path $AppPath 'backend'
$mcpDir = Join-Path $AppPath 'mcp_server'
$logDir = Join-Path $dataPath 'logs'

# nssm 은 등록할 때 패키지에서 _tools 로 복사한다. 그 뒤로는 _tools 것을 쓴다 —
# 패키지 폴더는 배포마다 바뀌지만 _tools 는 남는다.
$nssmInstalled = Join-Path $toolsPath 'nssm.exe'
$nssmPackaged = Join-Path $PSScriptRoot 'bin\nssm.exe'

# 차례가 곧 시작 순서다(멈출 때는 역순). Python·Dir 이 서비스마다 다르다 — MCP 는 제 가상환경.
$services = @(
    @{ Name = 'MatNexus'; Display = 'MatNexus API'; Script = 'run.py'; Log = 'service-server.log'
       Python = $venvPython; Dir = $backend
       Description = 'MatNexus 물성 데이터 플랫폼 — API 와 화면' }
)
if (-not $NoWorker) {
    $services += @{ Name = 'MatNexusWorker'; Display = 'MatNexus Worker'; Script = 'run_worker.py'; Log = 'service-worker.log'
                    Python = $venvPython; Dir = $backend
                    Description = 'MatNexus 작업 큐 워커 — 파싱·처리·알림' }
}
if (-not $NoMcp) {
    $services += @{ Name = 'MatNexusMcp'; Display = 'MatNexus MCP'; Script = 'server.py'; Log = 'service-mcp.log'
                    Python = $mcpPython; Dir = $mcpDir
                    Description = 'MatNexus AI 연결(MCP) — 물성을 AI 가 직접 묻는 자리' }
}

function Get-ServiceOrNull([string]$name) {
    return Get-Service -Name $name -ErrorAction SilentlyContinue
}

function Assert-Admin {
    $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal($identity)
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        throw '서비스를 등록·제거하려면 관리자 PowerShell 에서 실행해야 합니다.'
    }
}

function Resolve-DbService {
    if ($DbService -eq 'none') { return $null }
    if ($DbService) {
        if (-not (Get-ServiceOrNull $DbService)) { throw "PostgreSQL 서비스를 찾을 수 없습니다: $DbService" }
        return $DbService
    }
    $found = @(Get-Service -Name 'postgresql*' -ErrorAction SilentlyContinue)
    if ($found.Count -eq 1) { return $found[0].Name }
    if ($found.Count -gt 1) {
        Write-Warning ("PostgreSQL 서비스가 여럿입니다: " + (($found | ForEach-Object { $_.Name }) -join ', ') + " — 의존을 걸지 않습니다. -DbService 로 지정하세요.")
    } else {
        Write-Warning 'PostgreSQL 서비스를 찾지 못했습니다 — 의존을 걸지 않습니다. DB 가 다른 PC 에 있으면 정상입니다.'
    }
    return $null
}

function Install-Services {
    Assert-Admin
    if (-not (Test-Path $venvPython)) {
        throw "가상환경이 없습니다: $venvPython — deploy.ps1 을 먼저 실행하세요."
    }
    if (-not (Test-Path (Join-Path $backend 'run.py'))) { throw "backend\run.py 가 없습니다: $backend" }
    if (-not (Test-Path (Join-Path $backend '.env'))) { throw "backend\.env 가 없습니다. install.ps1 로 먼저 만드세요." }
    if (-not (Test-Path $nssmPackaged)) { throw "nssm.exe 가 패키지에 없습니다: $nssmPackaged" }
    foreach ($svc in $services) {
        if (-not (Test-Path $svc.Python)) { throw "$($svc.Name) 의 가상환경이 없습니다: $($svc.Python) — deploy.ps1 을 먼저 실행하세요(-NoMcp 로 뺄 수도 있습니다)." }
        if (-not (Test-Path (Join-Path $svc.Dir $svc.Script))) { throw "$($svc.Name) 의 진입점이 없습니다: $(Join-Path $svc.Dir $svc.Script)" }
    }

    New-Item -ItemType Directory -Force -Path $toolsPath | Out-Null
    New-Item -ItemType Directory -Force -Path $logDir | Out-Null
    Copy-Item -Force $nssmPackaged $nssmInstalled
    Write-Log "nssm 복사: $nssmInstalled"

    $db = Resolve-DbService

    # -NoWorker 로 다시 등록해도 전에 등록한 워커 서비스는 안 지운다 — 지우는 것은 -Action
    # Uninstall 의 일이다. 다만 남아 있다는 것은 말한다 — 모르고 두면 옛 코드의 워커가 돈다.
    if ($NoWorker -and (Get-ServiceOrNull 'MatNexusWorker')) {
        Write-Warning "-NoWorker 인데 MatNexusWorker 서비스가 남아 있습니다. 빼려면: Stop-Service MatNexusWorker ; & '$nssmInstalled' remove MatNexusWorker confirm"
    }
    if ($NoMcp -and (Get-ServiceOrNull 'MatNexusMcp')) {
        Write-Warning "-NoMcp 인데 MatNexusMcp 서비스가 남아 있습니다. 빼려면: Stop-Service MatNexusMcp ; & '$nssmInstalled' remove MatNexusMcp confirm"
    }

    foreach ($svc in $services) {
        $name = $svc.Name
        if (Get-ServiceOrNull $name) {
            Write-Log "$name 이미 있음 — 설정만 다시 맞춥니다."
            $state = (Get-Service $name).Status
            if ($state -eq 'Running') { Stop-Service $name -Force; Write-Log "$name 멈춤" }
        } else {
            Invoke-Native "$name 등록 실패" { & $nssmInstalled install $name $svc.Python $svc.Script }
            Write-Log "$name 등록"
        }
        $logPath = Join-Path $logDir $svc.Log
        $settings = @(
            @('Application', $svc.Python),
            @('AppParameters', $svc.Script),
            @('AppDirectory', $svc.Dir),
            @('DisplayName', $svc.Display),
            @('Description', $svc.Description),
            @('Start', 'SERVICE_DELAYED_AUTO_START'),
            @('AppStdout', $logPath),
            @('AppStderr', $logPath),
            @('AppRotateFiles', '1'),
            @('AppRotateOnline', '1'),
            @('AppRotateBytes', '10485760'),
            @('AppExit', 'Default', 'Restart'),
            @('AppRestartDelay', '10000'),
            @('AppEnvironmentExtra', 'PYTHONUTF8=1', 'PYTHONIOENCODING=utf-8')
        )
        foreach ($entry in $settings) {
            $nssmArgs = @('set', $name) + $entry
            Invoke-Native "$name 설정 실패: $($entry[0])" { & $nssmInstalled @nssmArgs }
        }
        if ($db) {
            Invoke-Native "$name 의존성 설정 실패" { & $nssmInstalled set $name DependOnService $db }
            Write-Log "$name 은 $db 뒤에 뜹니다."
        } else {
            Invoke-Native "$name 의존성 해제 실패" { & $nssmInstalled reset $name DependOnService }
        }
    }
    Write-Log '등록 완료'
    Start-Services
    if (-not $NoWatchdog) {
        & (Join-Path $PSScriptRoot 'watchdog.ps1') -AppPath $AppPath -Register
    }
}

function Start-Services {
    foreach ($svc in $services) {
        $name = $svc.Name
        $found = Get-ServiceOrNull $name
        if (-not $found) { Write-Warning "$name 이 등록돼 있지 않습니다 — -Action Install 을 먼저."; continue }
        if ($found.Status -eq 'Running') { Write-Log "$name 이미 실행 중"; continue }
        Start-Service $name
        Write-Log "$name 시작"
    }
    Show-Status
}

function Stop-Services {
    # 워커부터 멈춘다(목록의 역순) — 처리 중이던 작업은 다음 기동 때 reclaim_stalled 이 되살린다.
    $reversed = @($services)
    [array]::Reverse($reversed)
    foreach ($svc in $reversed) {
        $name = $svc.Name
        $found = Get-ServiceOrNull $name
        if (-not $found) { continue }
        if ($found.Status -ne 'Stopped') {
            Stop-Service $name -Force
            Write-Log "$name 멈춤"
        }
    }
}

function Uninstall-Services {
    Assert-Admin
    Stop-Services
    $nssm = if (Test-Path $nssmInstalled) { $nssmInstalled } else { $nssmPackaged }
    foreach ($svc in $services) {
        $name = $svc.Name
        if (-not (Get-ServiceOrNull $name)) { Write-Log "$name 없음"; continue }
        Invoke-Native "$name 제거 실패" { & $nssm remove $name confirm }
        Write-Log "$name 제거"
    }
    if (Get-ScheduledTask -TaskName 'MatNexus-Watchdog' -ErrorAction SilentlyContinue) {
        & (Join-Path $PSScriptRoot 'watchdog.ps1') -AppPath $AppPath -Unregister
    }
    Write-Host ''
    Write-Host '서비스를 뺐습니다. 이제부터는 창에서 run_server.ps1 · run_worker.ps1 로 띄웁니다.'
}

function Show-Status {
    Write-Host ''
    foreach ($svc in $services) {
        $found = Get-ServiceOrNull $svc.Name
        if (-not $found) {
            Write-Host ("  {0,-16} 등록 안 됨" -f $svc.Name)
            continue
        }
        $mode = (Get-CimInstance Win32_Service -Filter "Name='$($svc.Name)'" -ErrorAction SilentlyContinue).StartMode
        Write-Host ("  {0,-16} {1,-10} 시작 방식: {2}   로그: {3}" -f $svc.Name, $found.Status, $mode, (Join-Path $logDir $svc.Log))
    }
    $watch = Get-ScheduledTask -TaskName 'MatNexus-Watchdog' -ErrorAction SilentlyContinue
    Write-Host ("  {0,-16} {1}" -f '감시(작업)', $(if ($watch) { "$($watch.State) — 1분마다 /api/health, 로그: $(Join-Path $logDir 'watchdog.log')" } else { '등록 안 됨 — .\watchdog.ps1 -AppPath … -Register' }))
    Write-Host ''
    if (Get-ServiceOrNull 'MatNexus') {
        Write-Host '  멈추기/시작:  Stop-Service MatNexus ; Start-Service MatNexus   (워커는 MatNexusWorker, MCP 는 MatNexusMcp)'
        Write-Host "  또는:         .\service.ps1 -AppPath '$AppPath' -Action Restart"
    }
}

switch ($Action) {
    'Install'   { Install-Services }
    'Uninstall' { Uninstall-Services }
    'Start'     { Start-Services }
    'Stop'      { Stop-Services; Show-Status }
    'Restart'   { Stop-Services; Start-Services }
    'Status'    { Show-Status }
}
