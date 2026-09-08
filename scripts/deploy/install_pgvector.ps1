<#
pgvector 설치 — **파일 세 개를 PostgreSQL 에 넣고 확장을 켠다.**

`build_pgvector.ps1` 이 뽑아 둔 산출물을 받아 넣는다. **운영 서버에는 빌드 도구가
필요 없다.**

    vector.dll              → <PG>\lib\
    vector.control          → <PG>\share\extension\
    vector--<판>.sql        → <PG>\share\extension\
    CREATE EXTENSION vector;

## 관리자 권한이 필요하다

`Program Files` 아래에 쓰기 때문이다. 권한이 없으면 **아무것도 안 하고 멈춘다** —
반쯤 복사된 상태가 제일 나쁘다(확장이 있다고 나오는데 DLL 이 없으면 그 DB 는
연결마다 오류를 낸다).

## PostgreSQL 을 재시작하지 않아도 된다

확장 DLL 은 **연결이 처음 쓸 때** 로드된다. 이미 열려 있던 연결은 다음 요청부터
쓸 수 있다. 반대로 **업그레이드**(DLL 을 새 것으로 갈아 끼울 때)는 그 파일을 쓰고
있는 프로세스가 있으면 복사가 막히므로, 그때는 서비스를 잠깐 멈춘다.

사용 (관리자 PowerShell):
  .\install_pgvector.ps1 -FromDir '..\..\build\pgvector\pg17'
  .\install_pgvector.ps1 -FromDir ... -DatabaseUrl 'postgresql://postgres:root@localhost:5432/matnexus'
  .\install_pgvector.ps1 -CheckOnly
#>

param(
    [string]$FromDir,
    [string]$PgRoot,
    [string]$DatabaseUrl = $env:DATABASE_URL,
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'

function Write-Log([string]$m) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $m" }

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

# --- PostgreSQL 찾기 ---------------------------------------------------------
if (-not $PgRoot) {
    $found = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Name -replace '\D', '0') } -Descending | Select-Object -First 1
    if (-not $found) { throw 'PostgreSQL 을 못 찾았습니다. -PgRoot 로 알려 주세요.' }
    $PgRoot = $found.FullName
}
$libDir = Join-Path $PgRoot 'lib'
$extDir = Join-Path $PgRoot 'share\extension'
$psql = Join-Path $PgRoot 'bin\psql.exe'
Write-Log "PostgreSQL: $PgRoot"

$installed = Test-Path (Join-Path $libDir 'vector.dll')
Write-Log ("vector.dll : " + $(if ($installed) { '있음' } else { '없음' }))

if ($CheckOnly) {
    if (-not $installed) { Write-Log '설치되지 않았습니다.'; exit 1 }
    Get-ChildItem $extDir -Filter 'vector--*.sql' | ForEach-Object { Write-Log "  $($_.Name)" }
    exit 0
}

if (-not $FromDir) { throw '-FromDir 로 산출물 폴더를 주세요(build_pgvector.ps1 이 만든 곳).' }
$FromDir = [System.IO.Path]::GetFullPath($FromDir)
foreach ($needed in @('vector.dll', 'vector.control')) {
    if (-not (Test-Path (Join-Path $FromDir $needed))) { throw "$FromDir 에 $needed 이 없습니다." }
}
$sqlFiles = @(Get-ChildItem (Join-Path $FromDir 'vector--*.sql') -ErrorAction SilentlyContinue)
if ($sqlFiles.Count -eq 0) { throw "$FromDir 에 vector--*.sql 이 없습니다." }

# **판이 맞는지 먼저 본다.** 17 용 DLL 을 16 에 넣으면 `CREATE EXTENSION` 이
# 「모듈을 로드할 수 없음」 으로 죽는데, 그 메시지로는 판 불일치인 줄 모른다.
$infoPath = Join-Path $FromDir 'build-info.json'
if (Test-Path $infoPath) {
    $info = Get-Content $infoPath -Raw | ConvertFrom-Json
    $here = Split-Path $PgRoot -Leaf
    if ($info.postgres_major -and $info.postgres_major -ne $here) {
        throw "판이 다릅니다 — 산출물은 PostgreSQL $($info.postgres_major) 용인데 여기는 $here 입니다. 그 판으로 다시 빌드하세요."
    }
    Write-Log "산출물: pgvector $($info.pgvector) / PostgreSQL $($info.postgres_major) / $($info.built_at)"
}

# --- 권한 --------------------------------------------------------------------
# **반쯤 복사된 상태가 제일 나쁘다.** 확장은 있다고 나오는데 DLL 이 없으면 그
# 데이터베이스는 연결마다 오류를 낸다. 그래서 쓰기가 되는지 먼저 시험한다.
try {
    $probe = Join-Path $libDir '.mnx_write_test'
    New-Item -ItemType File -Path $probe -ErrorAction Stop | Out-Null
    Remove-Item $probe -Force
} catch {
    throw "$libDir 에 쓸 수 없습니다. **관리자 권한으로** PowerShell 을 다시 열고 돌리세요."
}

# --- 복사 --------------------------------------------------------------------
Write-Log '파일을 넣습니다.'
Copy-Item (Join-Path $FromDir 'vector.dll') $libDir -Force
Copy-Item (Join-Path $FromDir 'vector.control') $extDir -Force
foreach ($one in $sqlFiles) { Copy-Item $one.FullName $extDir -Force }
Write-Log "  $libDir\vector.dll"
Write-Log "  $extDir\vector.control (+ sql $($sqlFiles.Count)개)"

# --- 확장 켜기 ---------------------------------------------------------------
if (-not $DatabaseUrl) {
    Write-Host ''
    Write-Log '데이터베이스 주소를 안 줬습니다. 파일만 넣었으니, 쓸 DB 에서 한 번 켜세요:'
    Write-Host '    CREATE EXTENSION IF NOT EXISTS vector;'
    Write-Host ''
    exit 0
}

# SQLAlchemy 주소도 그대로 받는다 — .env 에서 복사해 붙이는 것이 사람의 실제 동작이다.
$clean = $DatabaseUrl -replace '^postgresql\+psycopg://', 'postgresql://'
Write-Log '확장을 켭니다.'
Invoke-Native '확장을 켜지 못했습니다' {
    & $psql $clean -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector'
}

$version = & $psql $clean -tAc "SELECT extversion FROM pg_extension WHERE extname='vector'"
Write-Host ''
Write-Log "켜졌습니다 — vector $($version.Trim())"
Write-Host ''
