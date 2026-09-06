Param(
    [int]$Port = 0,
    [string]$ApiBase,
    [switch]$Stdio
)
<#
개발 중 MCP 서버 기동.

    cd mcp_server
    .\run_mcp.ps1

**백엔드 포트를 외우지 않는다.** `backend\.env` 의 PORT 를 읽어 API 주소를
스스로 맞춘다(개발은 8011, 운영 설치는 8010) — 그 값이 다르면 도구가 전부
「백엔드에 닿지 못했습니다」 로 실패하는데, 그때 원인을 찾는 데 시간이 든다.

가상환경이 없으면 만들고 의존성까지 넣는다. **backend\.venv 와 섞지 않는다** —
MCP SDK 가 언제든 프레임워크 판을 올릴 수 있고(ReportArchive 는 그것으로
FastAPI 와 충돌했다), 그때 앱이 인질이 되면 안 된다.

    .\run_mcp.ps1 -Port 8013        다른 포트로
    .\run_mcp.ps1 -ApiBase '...'    백엔드 주소를 직접
    .\run_mcp.ps1 -Stdio            개인 연결(stdio) — HTTP 대신
#>

$ErrorActionPreference = 'Stop'
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$repo = Split-Path -Parent $here
$venvPython = Join-Path $here '.venv\Scripts\python.exe'

if (-not (Test-Path $venvPython)) {
    Write-Host '가상환경이 없습니다 — 만듭니다(backend 와 별도).'
    & py -m venv (Join-Path $here '.venv')
    if ($LASTEXITCODE -ne 0) { throw "가상환경을 만들지 못했습니다 (exit $LASTEXITCODE)" }
    & $venvPython -m pip install --quiet --upgrade pip
    & $venvPython -m pip install --quiet -r (Join-Path $here 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw "의존성 설치 실패 (exit $LASTEXITCODE)" }
    Write-Host '  준비됐습니다.'
}

# --- 백엔드 주소 --------------------------------------------------------------
# .env 의 PORT 를 그대로 따른다. 손으로 적어 두면 개발(8011)과 운영(8010) 사이에서
# 한쪽이 반드시 낡는다.
if (-not $ApiBase) {
    $backendPort = 8010
    $envFile = Join-Path $repo 'backend\.env'
    if (Test-Path $envFile) {
        $line = Select-String -Path $envFile -Pattern '^\s*PORT\s*=\s*(\d+)' | Select-Object -First 1
        if ($line) { $backendPort = [int]$line.Matches[0].Groups[1].Value }
    }
    $ApiBase = "http://127.0.0.1:$backendPort/api"
}
$env:MATNEXUS_API_BASE = $ApiBase

# 백엔드가 살아 있는지 먼저 본다 — 안 떠 있으면 도구가 전부 실패하고, 그 이유는
# MCP 로그에 안 남는다(도구를 불러야 드러난다).
try {
    $health = Invoke-RestMethod -Uri ($ApiBase + '/health') -TimeoutSec 3
    Write-Host "백엔드 $ApiBase — $($health.status) $($health.version)"
} catch {
    Write-Warning "백엔드에 닿지 못했습니다($ApiBase). 먼저 띄우세요 — 도구가 전부 실패합니다."
}

if ($Stdio) {
    $env:MATNEXUS_MCP_TRANSPORT = 'stdio'
    Push-Location $here
    try { & $venvPython server.py } finally { Pop-Location }
    return
}

if ($Port -gt 0) { $env:MATNEXUS_MCP_PORT = "$Port" }
$mcpPort = if ($env:MATNEXUS_MCP_PORT) { $env:MATNEXUS_MCP_PORT } else { '8012' }

# 이미 그 포트를 잡고 있으면 알려 준다. 안 그러면 「주소가 이미 사용 중」 이라는
# 영문 예외만 보이고, 옛 프로세스가 낡은 코드로 응답하는 것을 모른 채 헤맨다.
$owner = (Get-NetTCPConnection -State Listen -LocalPort ([int]$mcpPort) -ErrorAction SilentlyContinue).OwningProcess
if ($owner) {
    throw "포트 $mcpPort 를 이미 쓰고 있습니다(PID $owner). 먼저 멈추세요: Stop-Process -Id $owner -Force"
}

Write-Host "MCP http://127.0.0.1:$mcpPort/mcp"
Write-Host ('등록: claude mcp add --transport http matnexus ' +
    "http://127.0.0.1:$mcpPort/mcp --header 'Authorization: Bearer <내 PAT>'")
Push-Location $here
try { & $venvPython server.py } finally { Pop-Location }
