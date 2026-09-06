Param()
<#
배포된 MCP 서버의 기동 스크립트.

    cd <AppPath>
    .\run_mcp.ps1

**세 번째 창이다**(API·워커에 이어). AI 가 물성을 직접 묻게 하는 자리이고,
없어도 앱은 멀쩡히 돈다 — 이 창이 꺼져 있으면 Claude 쪽에서 「연결할 수 없다」
가 뜰 뿐이다.

**백엔드와 다른 가상환경을 쓴다.** MCP SDK 가 언제든 프레임워크 판을 올릴 수
있고(ReportArchive 는 그것으로 FastAPI 와 충돌했다), 그때 앱이 인질이 되면 안
된다. `_venvs\mcp` 는 deploy.ps1 이 만든다.

밖에 열려면 `MATNEXUS_MCP_HOST` 와 **`MATNEXUS_MCP_ALLOWED_HOSTS` 를 함께**
준다 — 허용 Host 없이 열면 서버가 거절한다(DNS rebinding 보호가 무의미해지므로).
#>

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$venvPython = Join-Path ($scriptDir + '_venvs') 'mcp\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Error "MCP 가상환경이 없습니다: $venvPython — deploy.ps1 을 다시 실행하거나, mcp_server 폴더에서 'py -m venv' 로 만드세요."
    exit 1
}

$serverDir = Join-Path $scriptDir 'mcp_server'
if (-not (Test-Path (Join-Path $serverDir 'server.py'))) {
    Write-Error 'mcp_server\server.py 를 찾을 수 없습니다. 패키지가 불완전합니다.'
    exit 1
}

# 백엔드 주소. 같은 기계의 8010 이 기본이고, .env 의 PORT 를 바꿨다면 여기도 준다.
if (-not $env:MATNEXUS_API_BASE) {
    $env:MATNEXUS_API_BASE = 'http://127.0.0.1:8010/api'
}

Write-Host "MCP 서버 — 백엔드 $($env:MATNEXUS_API_BASE)"
Write-Host "등록: claude mcp add --transport http matnexus http://127.0.0.1:8012/mcp --header 'Authorization: Bearer <내 PAT>'"

Push-Location $serverDir
try {
    & $venvPython server.py
} finally {
    Pop-Location
}
