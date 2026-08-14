<#
Day 0 — 신규 서버 설치.

**이 절차는 참고한 어느 프로젝트에도 없다.** 52의 배포 문서는 "이미 돌고 있는
설치를 갱신하는 절차"이며 신규 구축을 명시적으로 제외하고, 65는 docker compose
한 줄이라 도커가 없으면 성립하지 않는다. 그래서 새로 쓴다(개발계획 §9.1).

폴더 배치 — 운영 데이터는 앱 폴더 **바깥**에 둔다.

    <AppPath>              코드. 배포마다 통째로 교체된다
    <AppPath>_prev         직전 버전 (롤백용)
    <AppPath>_venvs\       가상환경
    <AppPath>_data\        filestore · logs   ← 배포와 무관하게 살아남는다

52는 배포마다 uploads 를 복사해 옮기지만, CAE 시험 데이터는 GB 단위라 그 방식이
성립하지 않는다. 바깥에 두면 복사 자체가 없다.

각 단계는 멱등하다. 중간에 끊겨 다시 실행해도 같은 결과가 나오고, 특히 이미 있는
관리자 계정의 비밀번호를 되돌리지 않는다.

스크립트는 `C:\Server\tools\MatNexus\` 처럼 **프로젝트별 하위 폴더**에 둔다.
`C:\Server\tools` 바로 아래에 두면 같은 서버의 다른 앱과 파일명이 겹쳐 서로를
덮어쓴다(실측).

사용:
  .\install.ps1 -AppPath 'C:\Server\MatNexus' -DbPassword '...'
  .\install.ps1 -AppPath 'C:\Server\MatNexus' -ZipPath 'C:\tmp\deploy_package.zip' `
                -DbHost localhost -DbUser postgres -DbPassword '...'
#>

param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [string]$ZipPath,
    [string]$Repo = '4leaf321-nox321/MatNexus',
    [string]$Tag,
    [string]$DbHost = 'localhost',
    [int]$DbPort = 5432,
    [string]$DbName = 'matnexus',
    [string]$DbUser = 'postgres',
    [Parameter(Mandatory = $true)][string]$DbPassword,
    [int]$Port = 8010,
    [string]$PythonExe,
    [string]$AdminEmail = 'admin@matnexus.local',
    [switch]$SkipPrecheck
)

$ErrorActionPreference = 'Stop'
function Write-Log([string]$m) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $m" }

<#
네이티브 명령 실행 — stderr 를 오류로 착각하지 않는다.

Windows PowerShell 5.1 은 $ErrorActionPreference='Stop' 상태에서 네이티브 명령이
stderr 에 한 줄만 써도 그것을 종료성 오류로 바꾼다. alembic 은 INFO 로그를
stderr 로 내보내므로, 출력을 로그 파일로 리다이렉트하는 순간 정상 설치가
실패로 뒤집힌다(실측). 성공 여부는 종료 코드로만 판정한다.
#>
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

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$dataPath = $AppPath + '_data'
$dsn = "postgresql+psycopg://${DbUser}:${DbPassword}@${DbHost}:${DbPort}/${DbName}"

# --- 1. 환경 점검 -------------------------------------------------------------
if (-not $SkipPrecheck) {
    Write-Log '환경 점검'
    & (Join-Path $scriptDir 'precheck.ps1') -AppPath $AppPath -DatabaseUrl $dsn -Port $Port
    if ($LASTEXITCODE -ne 0) { throw '환경 점검에서 문제가 발견됐습니다. 위 목록을 해결하고 다시 실행하세요.' }
}

# --- 2. 코드 배치 — deploy.ps1 을 그대로 쓴다 ----------------------------------
# 첫 설치와 갱신이 같은 경로를 타야 "설치는 되는데 갱신이 안 되는" 상태가 생기지
# 않는다. 마이그레이션은 .env 를 만든 뒤에 돌려야 하므로 여기서는 건너뛴다.
Write-Log '코드 배치'
$deployArgs = @{ AppPath = $AppPath; SkipMigrations = $true }
if ($ZipPath) { $deployArgs.ZipPath = $ZipPath }
if ($Repo) { $deployArgs.Repo = $Repo }
if ($Tag) { $deployArgs.Tag = $Tag }
if ($PythonExe) { $deployArgs.PythonExe = $PythonExe }
& (Join-Path $scriptDir 'deploy.ps1') @deployArgs
if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) { throw "코드 배치 실패 (exit $LASTEXITCODE)" }

# --- 3. 운영 데이터 폴더 -------------------------------------------------------
foreach ($sub in @('filestore', 'logs')) {
    $dir = Join-Path $dataPath $sub
    if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Force -Path $dir | Out-Null }
}
Write-Log "운영 데이터 폴더: $dataPath"

# --- 4. .env 생성 (있으면 건드리지 않는다) --------------------------------------
$envFile = Join-Path $AppPath 'backend\.env'
if (Test-Path $envFile) {
    Write-Log '.env 가 이미 있습니다 — 그대로 둡니다.'
} else {
    # JWT 비밀키는 난수로 만든다. 기본값이 운영에 새면 누구나 토큰을 위조할 수
    # 있어 앱이 기동을 거부한다(app/main.py).
    $bytes = New-Object byte[] 48
    [System.Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bytes)
    $secret = [Convert]::ToBase64String($bytes)

    $lines = @(
        'APP_ENV=production',
        "DATABASE_URL=$dsn",
        "JWT_SECRET=$secret",
        'HOST=0.0.0.0',
        "PORT=$Port",
        "LOG_DIR=$dataPath\logs",
        "FILESTORE_DIR=$dataPath\filestore",
        '# https 로 서비스하면 true 로 올린다',
        'REFRESH_COOKIE_SECURE=false'
    )
    # BOM 없이 쓴다. PowerShell 5.1 의 `Set-Content -Encoding utf8` 은 BOM 을 붙이는데,
    # 그러면 첫 줄 키가 조용히 무시된다(app/config.py 주석 참조). 읽는 쪽도
    # utf-8-sig 로 흡수하지만, 만드는 쪽에서 깨끗하게 두는 편이 낫다.
    [System.IO.File]::WriteAllLines($envFile, $lines, (New-Object System.Text.UTF8Encoding $false))
    Write-Log ".env 생성: $envFile"
}

$backendPython = Join-Path ($AppPath + '_venvs') 'backend\Scripts\python.exe'
if (-not (Test-Path $backendPython)) { throw "가상환경을 찾을 수 없습니다: $backendPython" }

# --- 5. 데이터베이스 ----------------------------------------------------------
Write-Log "데이터베이스 확인/생성: $DbName"
$createDb = @'
import sys
import psycopg
host, port, user, password, name = sys.argv[1:6]
with psycopg.connect(host=host, port=int(port), user=user, password=password,
                     dbname="postgres", autocommit=True) as conn:
    if conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (name,)).fetchone():
        print(f"이미 있음: {name}")
    else:
        conn.execute(f'CREATE DATABASE "{name}" ENCODING \'UTF8\'')
        print(f"생성: {name}")
'@
$tempScript = Join-Path $AppPath ('.mnx_createdb_' + [guid]::NewGuid().ToString('N') + '.py')
Set-Content -Path $tempScript -Value $createDb -Encoding utf8
try {
    Invoke-Native '데이터베이스 생성 실패' {
        & $backendPython $tempScript $DbHost $DbPort $DbUser $DbPassword $DbName
    }
} finally {
    Remove-Item -Force $tempScript -ErrorAction SilentlyContinue
}

# --- 6. 마이그레이션 ----------------------------------------------------------
Write-Log '마이그레이션 적용'
Push-Location (Join-Path $AppPath 'backend')
try {
    Invoke-Native '마이그레이션 실패' { & $backendPython -m alembic upgrade head }
} finally {
    Pop-Location
}

# --- 7. 설치 시드 (데모 데이터 아님) --------------------------------------------
Write-Log '설치 시드'
Push-Location (Join-Path $AppPath 'backend')
try {
    Invoke-Native '시드 실패' { & $backendPython scripts\seed_install.py --email $AdminEmail }
} finally {
    Pop-Location
}

# --- 8. 방화벽 ----------------------------------------------------------------
$ruleName = "MatNexus $Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Log "방화벽 규칙이 이미 있습니다: $ruleName"
} else {
    # -ErrorAction Stop 이 필요하다. CIM 계열 cmdlet 은 5.1에서
    # $ErrorActionPreference='Stop' 을 따르지 않고 비종료 오류를 내는 경우가 있어,
    # 그대로 두면 실패했는데도 아래 성공 로그가 찍힌다(실측).
    try {
        New-NetFirewallRule -DisplayName $ruleName -Direction Inbound -Action Allow `
            -Protocol TCP -LocalPort $Port -ErrorAction Stop | Out-Null
        Write-Log "방화벽 열기: TCP $Port"
    } catch {
        Write-Warning "방화벽 규칙을 만들지 못했습니다(관리자 권한 필요)."
        Write-Warning "관리자 PowerShell 에서 다음을 실행하세요:"
        Write-Warning "  New-NetFirewallRule -DisplayName '$ruleName' -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port"
    }
}

Write-Host ''
Write-Host '설치 완료.'
Write-Host ''
Write-Host "  시작        : cd '$AppPath' ; .\run_server.ps1"
Write-Host "  접속        : http://<서버주소>:$Port/"
Write-Host "  운영 데이터 : $dataPath  (백업 대상 — DB와 함께 받아야 복구가 성립한다)"
Write-Host ''
Write-Host '  위에 출력된 관리자 비밀번호는 다시 표시되지 않습니다. 첫 로그인 시 변경이 강제됩니다.'
Write-Host ''
