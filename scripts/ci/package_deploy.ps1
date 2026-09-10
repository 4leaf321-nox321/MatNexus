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
    deploy.ps1 / rollback.ps1 / venv_sync.ps1 / install.ps1 / precheck.ps1 /
    setup_ollama.ps1 / build_pgvector.ps1 / install_pgvector.ps1 /
    backup.ps1 / restore.ps1
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

# --- MCP 서버 -----------------------------------------------------------------
# **앱과 별도 venv 라 wheel 도 따로 담는다.** MCP 가 없어도 앱은 돌아야 하므로
# 여기서 실패해도 배포는 계속된다 — 다만 조용히 넘어가지 않고 경고를 남긴다.
Write-Host 'MCP 서버 포함'
# **폴더째 담고 쓰레기만 뺀다** — 백엔드와 같은 규칙이다.
#
# 전에는 파일을 하나씩 이름으로 골라 담았다(server.py·requirements.txt·README·
# GUIDE). 그러다 `retry_plan.py` 가 늘었는데 이 목록을 아무도 안 고쳤고,
# 운영 서버에서 `ModuleNotFoundError: retry_plan` 이 났다(실측 2026-09-10).
# CI 도 개발도 그 파일이 옆에 있으니 아무 데서도 안 드러난다 — **배포한 뒤에야** 안다.
#
# 이름을 두 곳에 적으면 한쪽이 낡는다. 그러니 적지 않는다.
Copy-Item -Recurse -Force .\mcp_server .\deploy\mcp_server
foreach ($junk in @('.venv', '__pycache__', '.pytest_cache', '.mypy_cache', '.ruff_cache', 'probe-server.log')) {
    Get-ChildItem -Path .\deploy\mcp_server -Filter $junk -Recurse -Force -ErrorAction SilentlyContinue |
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
}

python -m pip wheel -r .\deploy\mcp_server\requirements.txt -w .\deploy\mcp_server\packages
if ($LASTEXITCODE -ne 0) {
    Write-Warning 'MCP wheel 번들을 만들지 못했습니다 — 이 패키지로는 MCP 서버가 안 뜹니다(앱은 정상).'
} else {
    $mcpWheels = (Get-ChildItem .\deploy\mcp_server\packages -Filter '*.whl' -ErrorAction SilentlyContinue).Count
    Write-Host "  MCP wheel $mcpWheels 개"
}

# **서버가 불러오는 모듈이 다 들어갔나.** 폴더째 담으니 지금은 빠질 이유가
# 없지만, 누군가 다시 골라 담기 시작하면 같은 일이 또 난다. **배포한 뒤에야
# 알게 되는 종류**라 여기서 막는다 — CI 도 개발도 그 파일이 옆에 있으니
# 아무 데서도 안 드러난다.
$imported = Select-String -Path .\deploy\mcp_server\server.py -Pattern '^import\s+(\w+)$' |
    ForEach-Object { $_.Matches[0].Groups[1].Value }
foreach ($name in $imported) {
    $sibling = Join-Path '.\mcp_server' "$name.py"
    if ((Test-Path $sibling) -and -not (Test-Path (Join-Path '.\deploy\mcp_server' "$name.py"))) {
        Write-Error "패키지에 mcp_server\$name.py 가 빠졌습니다 — 서버가 import 합니다."
        exit 1
    }
}

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
#
# **httpx 가 여기 있는 이유는 앱이 아니라 스크립트 때문이다.** 이관·데모 스크립트는
# `fastapi.testclient.TestClient` 로 운영과 같은 길을 태우는데, 그것이 httpx 를
# 요구한다. httpx 가 개발 전용 의존성에 있던 동안 앱은 멀쩡히 떴고 **운영서버에서
# 이관만 못 돌았다**(2026-08-28, 실측):
#
#     RuntimeError: The starlette.testclient module requires the httpx2 package
#
# 문구가 `httpx2` 라 새 패키지를 찾게 되는데, starlette 1.6 은 httpx2 가 없으면
# **httpx 로 되돌아간다**(경고만 낸다). 개발이 httpx 로 돌고 있으므로 운영도 같은
# 것으로 돌린다 — httpx2 로 넘어가는 것은 스위트 전체가 걸린 별도 결정이다.
foreach ($mod in @('fastapi', 'uvicorn', 'sqlalchemy', 'alembic', 'psycopg', 'bcrypt', 'pyjwt', 'httpx')) {
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
Copy-Item -Force .\scripts\ci\run_mcp_template.ps1 .\deploy\run_mcp.ps1
Copy-Item -Force .\scripts\deploy\venv_sync.ps1 .\deploy\venv_sync.ps1
Copy-Item -Force .\scripts\deploy\deploy.ps1 .\deploy\deploy.ps1
Copy-Item -Force .\scripts\deploy\rollback.ps1 .\deploy\rollback.ps1
Copy-Item -Force .\scripts\deploy\install.ps1 .\deploy\install.ps1
Copy-Item -Force .\scripts\deploy\precheck.ps1 .\deploy\precheck.ps1
Copy-Item -Force .\scripts\deploy\backup.ps1 .\deploy\backup.ps1
Copy-Item -Force .\scripts\deploy\restore.ps1 .\deploy\restore.ps1

# 선택 부품(의미 검색) 설치. **한 번만 돌리는 것들이라 deploy.ps1 이 부르지 않지만**,
# zip 에 없으면 서버의 관리자가 그 스크립트를 손에 넣을 방법이 없다.
Copy-Item -Force .\scripts\deploy\setup_ollama.ps1 .\deploy\setup_ollama.ps1
Copy-Item -Force .\scripts\deploy\build_pgvector.ps1 .\deploy\build_pgvector.ps1
Copy-Item -Force .\scripts\deploy\install_pgvector.ps1 .\deploy\install_pgvector.ps1

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
