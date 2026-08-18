<#
백업 — 데이터베이스와 운영 데이터를 함께 받는다.

**둘 중 하나만 받으면 복구되지 않는다.** DB에는 곡선의 경로와 해시가, 파일스토어에는
그 곡선의 실제 내용이 있다(D10). 시점이 어긋나면 "DB에는 있는데 파일이 없는" 행이
생긴다. 그래서 한 스크립트가 같은 시각에 둘 다 받는다.

65·RA 양쪽 모두 이 절차가 없었다(비교표 D-백업: "양쪽 공통 공백"). 베낄 원본이
없어 새로 쓴다.

받는 것:
    <BackupRoot>\<타임스탬프>\db.dump        pg_dump 커스텀 포맷
    <BackupRoot>\<타임스탬프>\filestore\     시험 데이터 원본·Parquet
    <BackupRoot>\<타임스탬프>\.env           접속 정보·JWT 비밀키
    <BackupRoot>\<타임스탬프>\MANIFEST.txt   무엇을 언제 받았는지

사용:
  .\backup.ps1 -AppPath 'C:\Server\MatNexus' -BackupRoot 'D:\backup\matnexus'
  .\backup.ps1 -AppPath 'C:\Server\MatNexus' -BackupRoot 'D:\backup\matnexus' -KeepDays 30
#>

param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [Parameter(Mandatory = $true)][string]$BackupRoot,
    [int]$KeepDays = 30,
    [string]$PgDumpExe
)

$ErrorActionPreference = 'Stop'

<#
매개변수를 값으로 받아 버리는 것을 막는다 — **대시는 하나다.**

`--AppPath 'C:\Server\MatNexus'` 로 쓰면 PowerShell 은 오류를 내지 않는다.
'--AppPath' 라는 문자열이 첫 위치 매개변수에 들어가고, 뒤따르는 진짜 경로는
그 다음 위치 매개변수로 **밀려 들어간다.** deploy.ps1 에서는 그것이 -Repo 라서
`gh release download --repo C:\Server\MatNexus` 가 실행됐고, 사람은 "gh 가
안 된다" 를 보게 됐다(실측). 값이 잘못 들어갔다는 신호가 어디에도 없었다.

값이 대시로 시작하면 그건 경로도 저장소도 아니다. 그 자리에서 멈춘다.
#>
function Assert-NotFlag([string]$value, [string]$name) {
    if ($value -and $value.StartsWith('-')) {
        throw @"
-$name 값이 '$value' 입니다 — 대시를 두 번 쓰신 것 같습니다.

PowerShell 매개변수는 대시가 하나입니다:  -$name '<값>'
'--$name' 처럼 쓰면 그 글자 자체가 값이 되고, 뒤에 적은 진짜 값은 다른
매개변수로 밀려 들어갑니다. 아무것도 실행하지 않았습니다.
"@
    }
}

Assert-NotFlag $AppPath 'AppPath'
Assert-NotFlag $BackupRoot 'BackupRoot'
Assert-NotFlag $PgDumpExe 'PgDumpExe'
function Write-Log([string]$m) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $m" }

$envFile = Join-Path $AppPath 'backend\.env'
if (-not (Test-Path $envFile)) { throw "backend\.env 를 찾을 수 없습니다: $envFile" }

# .env 에서 접속 정보를 읽는다. 백업 스크립트가 별도 설정을 갖게 하면 앱과
# 다른 DB 를 받는 사고가 난다.
$dsn = ((Get-Content $envFile -Encoding UTF8 | Where-Object { $_ -match '^DATABASE_URL=' }) -replace '^DATABASE_URL=', '').Trim()
if (-not $dsn) { throw '.env 에 DATABASE_URL 이 없습니다.' }
if ($dsn -notmatch '://(?<user>[^:]+):(?<pw>[^@]*)@(?<host>[^:/]+):(?<port>\d+)/(?<db>.+)$') {
    throw "DATABASE_URL 을 해석하지 못했습니다."
}
$dbUser = $Matches['user']; $dbPw = $Matches['pw']
$dbHost = $Matches['host']; $dbPort = $Matches['port']; $dbName = $Matches['db']

$dataPath = $AppPath + '_data'
$stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
$target = Join-Path $BackupRoot $stamp
New-Item -ItemType Directory -Force -Path $target | Out-Null

# --- pg_dump 찾기 -------------------------------------------------------------
if (-not $PgDumpExe) {
    $candidate = Get-ChildItem 'C:\Program Files\PostgreSQL\*\bin\pg_dump.exe' -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($candidate) { $PgDumpExe = $candidate.FullName }
    elseif (Get-Command pg_dump -ErrorAction SilentlyContinue) { $PgDumpExe = 'pg_dump' }
}
if (-not $PgDumpExe) {
    throw 'pg_dump 를 찾지 못했습니다. -PgDumpExe 로 경로를 지정하세요.'
}

# --- 데이터베이스 -------------------------------------------------------------
Write-Log "데이터베이스 백업: $dbName"
$env:PGPASSWORD = $dbPw
$dumpPath = Join-Path $target 'db.dump'
$previous = $ErrorActionPreference
$ErrorActionPreference = 'Continue'   # pg_dump 는 진행 상황을 stderr 로 낸다
try {
    & $PgDumpExe --host=$dbHost --port=$dbPort --username=$dbUser --format=custom `
        --file=$dumpPath $dbName
    $code = $LASTEXITCODE
} finally {
    $ErrorActionPreference = $previous
    $env:PGPASSWORD = ''
}
if ($code -ne 0) { throw "pg_dump 실패 (exit $code)" }

# --- 운영 데이터 --------------------------------------------------------------
if (Test-Path (Join-Path $dataPath 'filestore')) {
    Write-Log '파일스토어 백업'
    Copy-Item -Recurse -Force (Join-Path $dataPath 'filestore') (Join-Path $target 'filestore')
} else {
    Write-Warning "파일스토어가 없습니다 ($dataPath\filestore). 아직 시험 데이터가 없다면 정상입니다."
}

Copy-Item -Force $envFile (Join-Path $target '.env')

# --- 기록 --------------------------------------------------------------------
$dumpMb = [math]::Round((Get-Item $dumpPath).Length / 1MB, 1)
$fileCount = (Get-ChildItem (Join-Path $target 'filestore') -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
@(
    "받은 시각   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "앱 경로     : $AppPath",
    "데이터베이스: $dbName @ ${dbHost}:${dbPort}  (db.dump, ${dumpMb}MB)",
    "파일스토어  : $fileCount 개 파일",
    '',
    '복구 방법:',
    "  1. 앱을 중지한다",
    "  2. createdb 후  pg_restore --host=$dbHost --port=$dbPort --username=$dbUser --dbname=<새DB> db.dump",
    "  3. filestore\ 를 <AppPath>_data\filestore 로 되돌린다",
    "  4. .env 의 DATABASE_URL 을 확인하고 앱을 시작한다",
    '',
    '주의: DB 와 파일스토어는 같은 시점의 것이어야 한다. 한쪽만 되돌리면',
    '      "DB에는 있는데 파일이 없는" 행이 생긴다.'
) | Set-Content -Path (Join-Path $target 'MANIFEST.txt') -Encoding utf8

# --- 오래된 백업 정리 ----------------------------------------------------------
if ($KeepDays -gt 0) {
    $cutoff = (Get-Date).AddDays(-$KeepDays)
    $old = Get-ChildItem $BackupRoot -Directory | Where-Object { $_.CreationTime -lt $cutoff }
    foreach ($dir in $old) {
        Write-Log "오래된 백업 삭제: $($dir.Name)"
        Remove-Item -Recurse -Force $dir.FullName
    }
}

Write-Log "백업 완료: $target (DB ${dumpMb}MB, 파일 $fileCount 개)"
Write-Host ''
Write-Host '  복구 절차는 MANIFEST.txt 에 함께 적혀 있습니다.'
Write-Host '  **한 번은 실제로 복구해 보세요.** 받아만 두고 복구를 해 본 적이 없는 백업은'
Write-Host '  백업이 아닙니다 — 65도 RA도 이 절차 자체가 없었습니다.'
Write-Host ''
