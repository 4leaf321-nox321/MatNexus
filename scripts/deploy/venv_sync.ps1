<#
가상환경을 배포된 코드에 맞춘다.

venv 는 앱 폴더 **바깥**에 둔다.

    <AppPath>            코드. 배포마다 통째로 교체된다
    <AppPath>_venvs\backend

바깥에 두면 배포가 venv 를 다시 만들거나 복사하지 않아도 되고 절대경로도 그대로
유지된다. `requirements.txt` 가 바뀔 때만 다시 만든다 — 그 파일의 해시를 venv
옆에 적어 두고 매번 비교한다.

설치는 패키지에 동봉된 wheel 번들에서만 한다(`pip install --no-index`).
사내망에서 pip 이 불안정해도 배포가 멈추지 않는다.

사용:
  .\venv_sync.ps1 -AppPath 'C:\Server\MatNexus' -PythonExe 'C:\Python312\python.exe'
  .\venv_sync.ps1 -AppPath 'C:\Server\MatNexus' -Force
#>

param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [string]$PythonExe = 'python',
    [switch]$Force
)

$ErrorActionPreference = 'Stop'
function Write-Log([string]$m) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $m" }

$venvRoot = $AppPath + '_venvs'

# 워커는 backend venv 를 함께 쓴다. **MCP 서버만 따로다** — SDK 가 언제든
# 프레임워크 판을 올릴 수 있고(ReportArchive 는 그것으로 FastAPI 와 충돌했다),
# 그때 앱이 인질이 되면 안 된다.
#
# **MCP 는 없어도 된다.** requirements.txt 가 없으면 위 루프가 건너뛰므로,
# 이 서버를 안 쓰는 설치에서는 아무 일도 일어나지 않는다.
$components = @('backend', 'mcp_server')
$synced = @()

foreach ($component in $components) {
  # **MCP 의 실패는 앱 배포를 세우지 않는다**(2026-11-15 전반 점검). 패키징은 MCP wheel 실패를
  # 경고로 넘기는데(「앱은 정상」) 여기는 throw 했다 — 이 시점은 서비스를 멈추고 폴더를 바꾼 뒤,
  # 마이그레이션 전이라 배포가 서비스 내린 채로 끝났다. backend 의 실패는 그대로 멈춘다.
  try {
    $componentDir = Join-Path $AppPath $component
    $req = Join-Path $componentDir 'requirements.txt'
    if (-not (Test-Path $req)) {
        Write-Log "$component : requirements.txt 없음 — 건너뜁니다."
        continue
    }

    $venvDir = Join-Path $venvRoot $component
    $venvPython = Join-Path $venvDir 'Scripts\python.exe'
    $stampFile = Join-Path $venvRoot "$component.requirements.sha256"
    $wanted = (Get-FileHash -Algorithm SHA256 $req).Hash

    $current = $null
    if (Test-Path $stampFile) { $current = (Get-Content $stampFile -Raw).Trim() }

    if ((-not $Force) -and (Test-Path $venvPython) -and $current -eq $wanted) {
        Write-Log "$component : 가상환경이 최신입니다 — 재사용."
        $synced += $component
        continue
    }

    if (-not (Test-Path $venvPython)) {
        Write-Log "$component : 가상환경 생성 ($venvDir)"
        New-Item -ItemType Directory -Force -Path $venvRoot | Out-Null
        & $PythonExe -m venv $venvDir
        if ($LASTEXITCODE -ne 0) { throw "$component 가상환경을 만들지 못했습니다 (exit $LASTEXITCODE)" }
    } else {
        Write-Log "$component : requirements 가 바뀌었습니다 — 다시 설치합니다."
    }

    $wheelDir = Join-Path $componentDir 'packages'
    if (-not (Test-Path $wheelDir)) {
        throw "$component wheel 번들이 없습니다 ($wheelDir). 패키지가 불완전합니다."
    }

    Write-Log "$component : 동봉된 wheel 로 의존성 설치"
    # 옵션 전체를 따옴표로 감싼다. 따옴표가 없으면 "--find-links=<경로>" 가 두
    # 인자로 쪼개져 pip 이 그 디렉터리를 패키지 이름으로 해석한다.
    & $venvPython -m pip install --no-index "--find-links=$wheelDir" -r $req
    if ($LASTEXITCODE -ne 0) {
        # 해시를 갱신하지 않는다 — 다음 실행이 "최신"으로 착각하지 않도록.
        throw "$component 의존성 설치 실패 (exit $LASTEXITCODE)"
    }

    Set-Content -Encoding ascii -Path $stampFile -Value $wanted
    Write-Log "$component : 가상환경 준비 완료"
    $synced += $component
  } catch {
    if ($component -ne 'mcp_server') { throw }
    Write-Warning "mcp_server 가상환경을 준비하지 못했습니다 — 앱 배포는 계속합니다(AI 연결만 안 뜹니다): $_"
  }
}

Write-Log ('동기화: ' + ($synced -join ', '))
