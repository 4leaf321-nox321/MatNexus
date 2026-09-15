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
  .\install_pgvector.ps1 -PgRoot 'D:\PostgreSQL\17'          # 패키지에 든 pgvector\pg17 을 쓴다
  .\install_pgvector.ps1 -FromDir '..\..\build\pgvector\pg17'   # 다른 곳의 산출물
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
#
# **DB 주소를 받았으면 그 서버에 직접 묻는다**(2026-09-15). PostgreSQL 이 둘인 서버(18 은
# C: 5432, 17 은 D: 5434)에서 `C:\Program Files\PostgreSQL` 을 훑어 가장 높은 판을 집으면
# 18 에 DLL 을 넣고 17 의 DB 에서 `CREATE EXTENSION` 이 「모듈을 로드할 수 없음」 으로 죽는다.
# `pg_config` 뷰의 PKGLIBDIR·SHAREDIR 이 그 인스턴스의 진짜 자리다 — 어느 psql 로 물어도 된다.
function Find-AnyPsql {
    foreach ($root in @('C:\Program Files\PostgreSQL', 'D:\PostgreSQL', 'D:\Program Files\PostgreSQL')) {
        $hit = Get-ChildItem "$root\*\bin\psql.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($hit) { return $hit.FullName }
    }
    if (Get-Command psql -ErrorAction SilentlyContinue) { return 'psql' }
    return $null
}
$serverMajor = $null
if (-not $PgRoot -and $DatabaseUrl) {
    $anyPsql = Find-AnyPsql
    if ($anyPsql) {
        $clean = $DatabaseUrl -replace '^postgresql\+psycopg://', 'postgresql://'
        # 확장을 켤 DB 가 아직 없어도 서버는 답한다 — postgres DB 로 묻는다.
        $probeUrl = $clean -replace '/[^/]+$', '/postgres'
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $answer = & $anyPsql $probeUrl -tA -c "select string_agg(name || '=' || setting, ';') from pg_config where name in ('PKGLIBDIR','SHAREDIR')" 2>$null
            $version = & $anyPsql $probeUrl -tA -c "show server_version_num" 2>$null
            $code = $LASTEXITCODE
        } finally { $ErrorActionPreference = $previous }
        if ($code -eq 0 -and $answer) {
            $parts = @{}
            foreach ($pair in ("$answer" -split ';')) { $k, $v = $pair -split '=', 2; $parts[$k] = $v }
            if ($parts['PKGLIBDIR'] -and $parts['SHAREDIR']) {
                # pg_config 는 8.3 단축 경로(C:\PROGRA~1\…)로 답하기도 한다 — 긴 이름으로 편다.
                $libDir = (Get-Item ($parts['PKGLIBDIR'] -replace '/', '\')).FullName
                $extDir = (Join-Path (Get-Item ($parts['SHAREDIR'] -replace '/', '\')).FullName 'extension')
                $PgRoot = Split-Path $libDir -Parent
                # server_version_num 170005 → 17 (정수 나눗셈 — 5.1 의 / 는 실수를 낸다).
                if ("$version" -match '^(\d+)') { $serverMajor = [string][math]::Floor([int]$Matches[1] / 10000) }
                Write-Log "PostgreSQL(접속한 서버가 말한 자리): lib=$libDir · 판 $serverMajor"
            }
        } else {
            Write-Warning "DB 에 물어보지 못해 설치 폴더를 훑습니다 — PostgreSQL 이 둘이면 -PgRoot 로 알려 주세요."
        }
    }
}
if (-not $PgRoot) {
    $found = Get-ChildItem 'C:\Program Files\PostgreSQL' -Directory -ErrorAction SilentlyContinue |
        Sort-Object { [int]($_.Name -replace '\D', '0') } -Descending | Select-Object -First 1
    if (-not $found) { throw 'PostgreSQL 을 못 찾았습니다. -PgRoot 로 알려 주세요.' }
    $PgRoot = $found.FullName
}
if (-not $libDir) { $libDir = Join-Path $PgRoot 'lib' }
if (-not $extDir) { $extDir = Join-Path $PgRoot 'share\extension' }
if (-not $serverMajor) { $serverMajor = Split-Path $PgRoot -Leaf }
$psql = Join-Path $PgRoot 'bin\psql.exe'
if (-not (Test-Path $psql)) { $psql = Find-AnyPsql }
Write-Log "PostgreSQL: $PgRoot (판 $serverMajor)"

$installed = Test-Path (Join-Path $libDir 'vector.dll')
Write-Log ("vector.dll : " + $(if ($installed) { '있음' } else { '없음' }))

if ($CheckOnly) {
    if (-not $installed) { Write-Log '설치되지 않았습니다.'; exit 1 }
    Get-ChildItem $extDir -Filter 'vector--*.sql' | ForEach-Object { Write-Log "  $($_.Name)" }
    exit 0
}

# **패키지에 든 산출물이 기본이다**(2026-09-15). `pgvector\pg<판>` 이 이 스크립트 옆에 있다 —
# 서버 이전 때 사람이 따로 나르던 유일한 것이었다. 다른 곳의 것을 쓰려면 -FromDir.
if (-not $FromDir) {
    $bundled = Join-Path $PSScriptRoot ('pgvector\pg' + $serverMajor)
    if (Test-Path (Join-Path $bundled 'vector.dll')) {
        $FromDir = $bundled
        Write-Log "패키지의 산출물을 씁니다: $FromDir"
    } else {
        throw "이 PostgreSQL 판($serverMajor)용 산출물이 패키지에 없습니다($bundled). build_pgvector.ps1 로 뽑아 -FromDir 로 주세요."
    }
}
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
    $here = $serverMajor
    if ($info.postgres_major -and "$($info.postgres_major)" -ne "$here") {
        throw "판이 다릅니다 — 산출물은 PostgreSQL $($info.postgres_major) 용인데 여기는 $here 입니다. 그 판으로 다시 빌드하세요."
    }
    Write-Log "산출물: pgvector $($info.pgvector) / PostgreSQL $($info.postgres_major) / $($info.built_at)"
}

# --- 복사 --------------------------------------------------------------------
# **같은 파일이 이미 있으면 안 건드린다**(실측 2026-09-16). 같은 PostgreSQL 을 다른 앱(TestScope)이
# 먼저 쓰고 있으면 vector.dll 이 postgres 프로세스에 로드돼 있어 덮어쓰기가 「다른 프로세스에서
# 사용 중」 으로 막힌다 — 그런데 내용이 같으니 덮어쓸 이유가 없다. 다른 판이면(업그레이드) 그때만
# 복사하고, 그 경우 서비스를 잠깐 멈춰야 한다.
$srcDll = Join-Path $FromDir 'vector.dll'
$dstDll = Join-Path $libDir 'vector.dll'
$same = (Test-Path $dstDll) -and ((Get-FileHash $srcDll).Hash -eq (Get-FileHash $dstDll).Hash)
if ($same) {
    Write-Log "같은 vector.dll 이 이미 있습니다 — 파일은 그대로 두고 확장만 켭니다."
} else {
    # **반쯤 복사된 상태가 제일 나쁘다.** 확장은 있다고 나오는데 DLL 이 없으면 그
    # 데이터베이스는 연결마다 오류를 낸다. 그래서 쓰기가 되는지 먼저 시험한다.
    try {
        $probe = Join-Path $libDir '.mnx_write_test'
        New-Item -ItemType File -Path $probe -ErrorAction Stop | Out-Null
        Remove-Item $probe -Force
    } catch {
        throw "$libDir 에 쓸 수 없습니다. **관리자 권한으로** PowerShell 을 다시 열고 돌리세요."
    }

    Write-Log '파일을 넣습니다.'
    try {
        Copy-Item $srcDll $libDir -Force -ErrorAction Stop
    } catch {
        throw "vector.dll 을 덮어쓰지 못했습니다 — 다른 판이 로드된 채입니다. PostgreSQL 서비스를 잠깐 멈추고 다시 돌리세요: $_"
    }
    Copy-Item (Join-Path $FromDir 'vector.control') $extDir -Force
    foreach ($one in $sqlFiles) { Copy-Item $one.FullName $extDir -Force }
    Write-Log "  $dstDll"
    Write-Log "  $extDir\vector.control (+ sql $($sqlFiles.Count)개)"
}

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
