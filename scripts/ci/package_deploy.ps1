Param(
    # 릴리스 태그(v0.1.16). 없으면 frontend/package.json 의 version 을 쓴다.
    [string]$Tag
)
<#
배포 패키지(deploy_package.zip)를 만든다.

담기는 것:
    backend\             코드 + requirements.txt
    backend\packages\    wheel 번들 — 서버는 --no-index 로 여기서만 설치한다
    frontend\dist\       빌드된 SPA. 백엔드가 같은 프로세스에서 서빙한다
    run_server.ps1       기동
    deploy.ps1 / rollback.ps1 / venv_sync.ps1 / install.ps1 / precheck.ps1 / backup.ps1
    배포.md              초기 배포·업데이트 배포 절차
    BUILD_INFO.txt       wheel 을 만든 파이썬 마이너 버전

배포 스크립트를 패키지에 함께 넣는 이유: 서버가 릴리스만 받는 환경이어도
zip 하나를 손으로 펼쳐 스크립트를 꺼내면 그다음부터는 그 스크립트가 배포를
처리할 수 있다. 없으면 첫 배포에 저장소를 클론하는 수밖에 없다.
#>

Set-StrictMode -Version Latest

# ErrorActionPreference 를 'Stop' 으로 두지 않는다. Windows PowerShell 5.1 은
# 네이티브 명령이 stderr 에 쓰기만 해도 그것을 오류 레코드로 감싸는데, Stop 이면
# pip 의 단순 경고 한 줄에도 패키징이 멈춘다(실측). 대신 native 호출마다
# $LASTEXITCODE 를 직접 확인한다 — 아래 모든 호출이 그렇게 돼 있다.

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Push-Location (Join-Path $root '..\..')

Write-Host '배포 패키지 생성 (Windows)'

Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .\deploy
New-Item -ItemType Directory -Path .\deploy | Out-Null

Write-Host '백엔드 코드 복사'
Copy-Item -Recurse -Force .\backend .\deploy\backend
# 개발 산출물은 패키지에서 뺀다. 운영 데이터(.env·filestore·logs)는 서버의
# <AppPath>_data 에 있으므로 애초에 여기 없다.
foreach ($junk in @('.venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'logs', 'filestore', '.env')) {
    Get-ChildItem -Path .\deploy\backend -Filter $junk -Recurse -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

# --- 프론트엔드 ---------------------------------------------------------------
# 백엔드가 <패키지 루트>\frontend\dist 에서 SPA 를 서빙한다. 이게 없으면 배포된
# 앱이 모든 페이지에 API 의 JSON 404 를 돌려준다.
Write-Host '프론트엔드 빌드'
Push-Location .\frontend
$env:NODE_OPTIONS = '--max-old-space-size=4096'
npm ci
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Error "npm ci 실패 (exit $LASTEXITCODE)"; exit 1 }
npm run build
if ($LASTEXITCODE -ne 0) { Pop-Location; Write-Error "npm run build 실패 (exit $LASTEXITCODE)"; exit 1 }
Pop-Location

if (-not (Test-Path .\frontend\dist\index.html)) {
    Write-Error '프론트엔드 빌드에 dist\index.html 이 없습니다.'
    exit 1
}

# 프론트는 API 절대주소를 굽지 않는다(항상 상대경로 /api). 굽는 방식이면 값이
# 빠졌을 때 사용자 브라우저가 자기 PC를 부르게 되므로, 그런 흔적이 남아 있지
# 않은지 확인한다.
$leaked = Get-ChildItem .\frontend\dist\assets -Filter '*.js' -ErrorAction SilentlyContinue |
    Where-Object { Select-String -Path $_.FullName -Pattern 'localhost:8010' -Quiet -SimpleMatch }
if ($leaked) {
    Write-Error "번들에 localhost:8010 이 남아 있습니다 ($($leaked[0].Name)). API 주소를 굽지 않도록 고치세요."
    exit 1
}
Write-Host '프론트엔드 API 주소 검사 통과'

New-Item -ItemType Directory -Force -Path .\deploy\frontend | Out-Null
Copy-Item -Recurse -Force .\frontend\dist .\deploy\frontend\dist

# --- wheel 번들 ---------------------------------------------------------------
# 패키지에 설치하는 대신 wheel 을 모아 담는다. 서버가 `pip install --no-index
# --find-links=packages` 로 진짜 가상환경을 만들므로 배포가 네트워크를 쓰지 않는다.
# 사내망에서 pip 이 중간에 끊기는 것을 배포 경로에 끼워 넣지 않기 위해서다.
python -m pip install --upgrade pip

$wheelDir = '.\deploy\backend\packages'
Write-Host 'wheel 번들 생성'
python -m pip wheel -r .\deploy\backend\requirements.txt -w $wheelDir
if ($LASTEXITCODE -ne 0) { Write-Error "pip wheel 실패 (exit $LASTEXITCODE)"; exit 1 }

$wheels = Get-ChildItem -Path $wheelDir -Filter '*.whl' -ErrorAction SilentlyContinue
# 가상환경을 만들 수 없는 번들을 출하하느니 빌드를 실패시킨다.
foreach ($mod in @('fastapi', 'uvicorn', 'sqlalchemy', 'alembic', 'psycopg', 'bcrypt', 'pyjwt')) {
    $needle = ($mod -replace '_', '-')
    if (-not ($wheels | Where-Object { ($_.Name -replace '_', '-') -like "$needle-*" })) {
        Write-Error "packages 에 '$mod' wheel 이 없습니다."
        exit 1
    }
}
Write-Host "  wheel $($wheels.Count) 개, 의존성 검사 통과"

# --- 스크립트와 빌드 정보 ------------------------------------------------------
Write-Host '실행·배포 스크립트 추가'
Copy-Item -Force .\scripts\ci\run_server_template.ps1 .\deploy\run_server.ps1
Copy-Item -Force .\scripts\ci\run_worker_template.ps1 .\deploy\run_worker.ps1
Copy-Item -Force .\scripts\deploy\venv_sync.ps1 .\deploy\venv_sync.ps1
Copy-Item -Force .\scripts\deploy\deploy.ps1 .\deploy\deploy.ps1
Copy-Item -Force .\scripts\deploy\rollback.ps1 .\deploy\rollback.ps1
Copy-Item -Force .\scripts\deploy\install.ps1 .\deploy\install.ps1
Copy-Item -Force .\scripts\deploy\precheck.ps1 .\deploy\precheck.ps1
Copy-Item -Force .\scripts\deploy\backup.ps1 .\deploy\backup.ps1

# 배포 문서도 함께 넣는다. 폐쇄망 서버는 zip 하나만 받으므로, 문서가 저장소에만
# 있으면 **정작 설치하는 자리에서 볼 수 없다.**
Copy-Item -Force .\배포.md .\deploy\배포.md

# 바이너리 wheel 은 ABI 태그(cp312 등)를 달고 있어 다른 마이너 버전에는 설치되지
# 않는다. deploy.ps1 이 이 값을 서버 파이썬과 비교한다.
$buildPython = & python -c "import sys; print('{}.{}'.format(sys.version_info[0], sys.version_info[1]))"
if ($LASTEXITCODE -ne 0) { Write-Error '빌드 파이썬 버전을 확인하지 못했습니다'; exit 1 }
Write-Host "빌드 파이썬 기록: $buildPython"
# **패키지가 자기 버전을 들고 있어야 한다.** 배포한 뒤 "서버에 뭐가 깔렸나" 를
# 물으면 답할 데가 있어야 하는데, 전에는 어디에도 없었다 — deploy 로그도, health
# 응답도, 파일도 버전을 안 남겼다. 태그 없이 배포하면 되짚을 방법이 아예 없다.
if (-not $Tag) {
    $Tag = 'v' + (node -p "require('./frontend/package.json').version")
    if ($LASTEXITCODE -ne 0) { Write-Error '버전을 읽지 못했습니다'; exit 1 }
}
Write-Host "패키지 버전: $Tag"
Set-Content -Encoding utf8 -Path .\deploy\BUILD_INFO.txt -Value @(
    "python=$buildPython"
    "version=$Tag"
)

# --- zip ---------------------------------------------------------------------
Write-Host 'zip 생성'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$deployDir = (Resolve-Path .\deploy).Path
$zipPath = Join-Path $deployDir 'deploy_package.zip'
# 압축 대상 폴더 안에 직접 만들면 아카이브가 자기 자신을 담으려다 실패한다.
$stagingZip = Join-Path ([System.IO.Path]::GetDirectoryName($deployDir)) 'deploy_package.zip'
Remove-Item -Force -ErrorAction SilentlyContinue $stagingZip
[System.IO.Compression.ZipFile]::CreateFromDirectory($deployDir, $stagingZip)
Move-Item -Force $stagingZip $zipPath

if (Test-Path $zipPath) {
    $sizeMb = [math]::Round((Get-Item $zipPath).Length / 1MB, 1)
    Write-Host "패키지 완료: $zipPath (${sizeMb}MB)"
} else {
    Write-Error "패키지 생성 실패: $zipPath"
    exit 1
}
Pop-Location
