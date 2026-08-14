<#
설치·배포 전 환경 점검.

65는 `check_compose_environment.py` 로 설치 전 환경을 검증했고 그것이 강점으로
평가됐다(비교표 C-4). 여기서는 윈도우·PostgreSQL 기준으로 같은 일을 한다.

문제를 찾으면 목록으로 보여 주고 0이 아닌 코드로 끝난다. 설치 도중에 절반만
적용된 상태로 멈추는 것보다, 시작 전에 막는 편이 원인 추적이 쉽다.

사용:
  .\precheck.ps1 -AppPath 'C:\Server\MatNexus' -DatabaseUrl 'postgresql+psycopg://...'
#>

param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [string]$DatabaseUrl,
    [string]$PythonVersion = '3.12',
    [int]$Port = 8010,
    [int]$RequiredFreeGb = 5
)

$ErrorActionPreference = 'Stop'
$problems = @()
$notes = @()

function Add-Problem([string]$m) { $script:problems += $m }
function Add-Note([string]$m) { $script:notes += $m }

# --- Python — wheel 번들의 ABI 태그가 마이너 버전에 묶여 있다 ------------------
$pythonExe = $null
try {
    $resolved = & py "-$PythonVersion" -c "import sys; print(sys.executable)" 2>$null
    if ($LASTEXITCODE -eq 0 -and $resolved) { $pythonExe = $resolved.Trim() }
} catch { }
if ($pythonExe) {
    Add-Note "Python $PythonVersion : $pythonExe"
} else {
    Add-Problem "Python $PythonVersion 을 찾지 못했습니다. 설치하거나 -PythonExe 로 지정하세요 (py -0p 로 목록 확인)."
}

# --- 디스크 여유 --------------------------------------------------------------
$drive = (Split-Path -Qualifier $AppPath)
if ($drive) {
    $free = (Get-PSDrive -Name $drive.TrimEnd(':') -ErrorAction SilentlyContinue).Free
    if ($null -ne $free) {
        $freeGb = [math]::Round($free / 1GB, 1)
        if ($freeGb -lt $RequiredFreeGb) {
            Add-Problem "$drive 여유 공간 ${freeGb}GB — 앱 2벌·가상환경·시험 데이터에 최소 ${RequiredFreeGb}GB 가 필요합니다."
        } else {
            Add-Note "$drive 여유 공간 : ${freeGb}GB"
        }
    }
}

# --- 쓰기 권한 ----------------------------------------------------------------
$parent = Split-Path -Parent $AppPath
if (-not (Test-Path $parent)) {
    try { New-Item -ItemType Directory -Force -Path $parent | Out-Null } catch { }
}
if (Test-Path $parent) {
    $probe = Join-Path $parent ('.mnx_probe_' + [guid]::NewGuid().ToString('N'))
    try {
        New-Item -ItemType File -Path $probe -Force | Out-Null
        Remove-Item -Force $probe
        Add-Note "쓰기 권한 : $parent"
    } catch {
        Add-Problem "$parent 에 쓸 수 없습니다. 관리자 권한으로 실행하거나 다른 경로를 쓰세요."
    }
} else {
    Add-Problem "$parent 를 만들 수 없습니다."
}

# --- 포트 --------------------------------------------------------------------
$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($listener) {
    $owner = (Get-Process -Id $listener[0].OwningProcess -ErrorAction SilentlyContinue).ProcessName
    Add-Problem "포트 $Port 을 이미 쓰고 있습니다 (프로세스: $owner). 중지하거나 다른 포트를 지정하세요."
} else {
    Add-Note "포트 $Port : 비어 있음"
}

# --- PostgreSQL ---------------------------------------------------------------
# 도달 가능성부터 확인한다. 폐쇄망에서 가장 흔한 실패가 "설치는 다 됐는데 DB 에
# 닿지 않는" 것이고, 그건 자격 증명 문제가 아니라 네트워크 문제다. TCP 연결은
# 외부 의존성 없이 .NET 으로 확인할 수 있다.
if ($DatabaseUrl) {
    if ($DatabaseUrl -match '@([^:/@]+):(\d+)/') {
        $dbHost = $Matches[1]
        $dbPort = [int]$Matches[2]
        $tcp = New-Object System.Net.Sockets.TcpClient
        try {
            if ($tcp.ConnectAsync($dbHost, $dbPort).Wait(3000)) {
                Add-Note "PostgreSQL 도달 : ${dbHost}:${dbPort}"
            } else {
                Add-Problem "PostgreSQL 에 닿지 않습니다 (${dbHost}:${dbPort}). 서비스 기동·방화벽·주소를 확인하세요."
            }
        } catch {
            Add-Problem "PostgreSQL 에 닿지 않습니다 (${dbHost}:${dbPort}) — $($_.Exception.Message)"
        } finally {
            $tcp.Close()
        }
    } else {
        Add-Note 'PostgreSQL : DATABASE_URL 에서 호스트·포트를 읽지 못해 도달 확인을 건너뜀'
    }

    # 자격 증명까지 보려면 psycopg 이 필요하다. 시스템 파이썬에는 없는 것이
    # 정상이며, 그때는 설치 과정의 DB 생성 단계에서 걸러진다.
    if ($pythonExe) {
        $probeScript = @'
import sys
from urllib.parse import urlsplit
url = urlsplit(sys.argv[1].replace("postgresql+psycopg://", "postgresql://"))
try:
    import psycopg
except ImportError:
    print("SKIP psycopg 미설치 - 설치 후 다시 확인됩니다")
    sys.exit(0)
try:
    with psycopg.connect(host=url.hostname, port=url.port or 5432,
                         user=url.username, password=url.password,
                         dbname="postgres", connect_timeout=5) as conn:
        version = conn.execute("SHOW server_version").fetchone()[0]
    print(f"OK PostgreSQL {version}")
except Exception as exc:
    print(f"FAIL {type(exc).__name__}: {exc}")
    sys.exit(1)
'@
        $tempProbe = Join-Path $env:TEMP ('mnx_pgprobe_' + [guid]::NewGuid().ToString('N') + '.py')
        Set-Content -Path $tempProbe -Value $probeScript -Encoding utf8
        $result = & $pythonExe $tempProbe $DatabaseUrl 2>&1
        Remove-Item -Force $tempProbe -ErrorAction SilentlyContinue
        if ($result -match '^OK') { Add-Note ($result -replace '^OK ', 'PostgreSQL 인증 : ') }
        elseif ($result -match '^SKIP') { Add-Note ($result -replace '^SKIP ', 'PostgreSQL 인증 : ') }
        else { Add-Problem "PostgreSQL 인증에 실패했습니다 — $result" }
    }
} else {
    Add-Note 'PostgreSQL : -DatabaseUrl 을 주지 않아 건너뜀'
}

# --- 결과 --------------------------------------------------------------------
Write-Host ''
foreach ($n in $notes) { Write-Host "  [ok]   $n" }
foreach ($p in $problems) { Write-Host "  [문제] $p" -ForegroundColor Yellow }
Write-Host ''

if ($problems.Count -gt 0) {
    Write-Host "$($problems.Count) 건을 해결한 뒤 다시 실행하세요." -ForegroundColor Yellow
    exit 1
}
Write-Host '환경 점검 통과.'
