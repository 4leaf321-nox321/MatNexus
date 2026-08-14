Param()
<#
배포된 백엔드의 기동 스크립트.

    cd <AppPath>
    .\run_server.ps1

의존성은 deploy.ps1(또는 venv_sync.ps1)이 앱 폴더 옆에 만든 가상환경
(<AppPath>_venvs\backend)에서 온다. PYTHONPATH 가 아니라 venv 를 쓰는 이유는
인터프리터의 site-packages 가 섞여 들어오지 않게 하기 위해서다.

FastAPI 는 ASGI 라 52가 쓰는 waitress(WSGI)를 쓸 수 없다. uvicorn 으로 띄운다.

D9(콘솔 실행)의 대가: 이 창을 닫으면 서버가 멈추고, 서버를 재부팅하면 수동으로
다시 실행해야 한다. 로그는 <AppPath>_data\logs 에 남으므로 창을 닫아도 기록은
사라지지 않는다.
#>

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path ($scriptDir + '_venvs') 'backend\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Error "가상환경이 없습니다: $venvPython — venv_sync.ps1 -AppPath '$scriptDir' 를 먼저 실행하세요."
    exit 1
}

$actual = & $venvPython -c "import sys; print('{}.{}'.format(sys.version_info[0], sys.version_info[1]))" 2>$null
Write-Host "사용 인터프리터: $venvPython (Python $actual)"

$buildInfo = Join-Path $scriptDir 'BUILD_INFO.txt'
if (Test-Path $buildInfo) {
    $buildPython = ((Get-Content $buildInfo | Where-Object { $_ -match '^python=' }) -replace '^python=', '').Trim()
    if ($buildPython -and $actual -and $actual -ne $buildPython) {
        Write-Warning "wheel 은 Python $buildPython 로 만들었는데 이 가상환경은 $actual 입니다."
    }
}

$backend = Join-Path $scriptDir 'backend'
if (-not (Test-Path (Join-Path $backend 'run.py'))) {
    Write-Error "backend\run.py 를 찾을 수 없습니다. 패키지가 불완전합니다."
    exit 1
}

if (-not (Test-Path (Join-Path $backend '.env'))) {
    Write-Error "backend\.env 가 없습니다. install.ps1 로 만들거나 이전 설치에서 복사하세요."
    exit 1
}

Push-Location $backend
try {
    & $venvPython run.py
} finally {
    Pop-Location
}
