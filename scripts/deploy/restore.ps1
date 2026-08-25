<#
복구 — 백업 하나를 되돌리고 **되돌아왔는지 확인한다.**

`backup.ps1` 의 마지막 줄이 이렇게 말한다: *"한 번은 실제로 복구해 보세요.
받아만 두고 복구를 해 본 적이 없는 백업은 백업이 아닙니다."* 그런데 그 「복구」
절차가 MANIFEST.txt 에 적힌 명령 두 줄뿐이었다 — 사람이 손으로 치는 것이고,
치다 틀리면 절반만 돌아온 상태가 된다.

## 이 스크립트가 하는 일의 절반은 검사다

되돌리는 것 자체는 `pg_restore` 와 파일 복사다. **어려운 것은 둘의 시점이
맞는지다.** DB 에는 곡선의 경로와 해시가 있고 파일스토어에는 그 곡선의 내용이
있다(D10) — 한쪽만 되돌리면 「DB에는 있는데 파일이 없는」 행이 생기고, 그 상태로
앱이 뜬다. 화면은 멀쩡하고 그 곡선을 열 때만 터진다.

그래서 복구가 끝나면 **DB 가 가리키는 파일이 실제로 있는지 세어 본다.** 하나라도
없으면 그 사실을 말한다.

## 있는 DB 를 덮지 않는다

`-DbName` 이 이미 있으면 **멈춘다.** 복구는 대개 "옛 상태를 옆에 띄워 보는" 일이고,
그때 실수로 살아 있는 DB 를 덮으면 되돌릴 데가 없다. 정말 덮으려면 -Force 를
쓰되, 그때도 무엇을 지우는지 먼저 적는다.

사용:
  # 백업 하나를 새 DB 로 되돌려 본다 (리허설)
  .\restore.ps1 -BackupPath 'D:\backup\matnexus\20260825-020000' -DbName matnexus_restore_check

  # 파일스토어까지 되돌린다 (실제 복구)
  .\restore.ps1 -BackupPath 'D:\backup\matnexus\20260825-020000' -DbName matnexus `
                -AppPath 'C:\Server\MatNexus' -Force
#>

param(
    [Parameter(Mandatory = $true)][string]$BackupPath,
    [Parameter(Mandatory = $true)][string]$DbName,
    [string]$AppPath,
    [switch]$Force,
    [string]$PgRestoreExe,
    [string]$PsqlExe
)

$ErrorActionPreference = 'Stop'

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

Assert-NotFlag $BackupPath 'BackupPath'
Assert-NotFlag $DbName 'DbName'
Assert-NotFlag $AppPath 'AppPath'

function Write-Log([string]$m) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $m" }

<#
네이티브 명령을 감싼다.

Windows PowerShell 5.1 은 네이티브 명령이 stderr 로 한 줄만 내도 그것을 종료성
오류로 바꾼다. `pg_restore` 는 진행 상황을 stderr 로 내므로 그대로 두면 성공한
복구가 실패로 보인다 — 판정은 **종료 코드로만** 한다.
#>
function Invoke-Native([string]$exe, [string[]]$arguments, [string]$what) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $exe @arguments
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($code -ne 0) { throw "$what 실패 (exit $code)" }
}

# --- 백업 확인 ----------------------------------------------------------------
if (-not (Test-Path $BackupPath)) { throw "백업 폴더를 찾을 수 없습니다: $BackupPath" }
$dumpPath = Join-Path $BackupPath 'db.dump'
if (-not (Test-Path $dumpPath)) { throw "db.dump 가 없습니다: $dumpPath" }

$envFile = Join-Path $BackupPath '.env'
if (-not (Test-Path $envFile)) { throw "백업에 .env 가 없습니다: $envFile" }

# 접속 정보는 **백업이 들고 온 것**을 쓴다. 여기서 따로 받으면 백업을 받은
# 서버와 다른 DB 에 되돌리는 사고가 난다.
$dsn = ((Get-Content $envFile -Encoding UTF8 | Where-Object { $_ -match '^DATABASE_URL=' }) -replace '^DATABASE_URL=', '').Trim()
if (-not $dsn) { throw '백업의 .env 에 DATABASE_URL 이 없습니다.' }
if ($dsn -notmatch '://(?<user>[^:]+):(?<pw>[^@]*)@(?<host>[^:/]+):(?<port>\d+)/(?<db>.+)$') {
    throw 'DATABASE_URL 을 해석하지 못했습니다.'
}
$dbUser = $Matches['user']; $dbPw = $Matches['pw']
$dbHost = $Matches['host']; $dbPort = $Matches['port']; $sourceDb = $Matches['db']

Write-Log "백업 원본: $sourceDb @ ${dbHost}:${dbPort}"
Write-Log "되돌릴 곳: $DbName"

# --- 도구 찾기 ----------------------------------------------------------------
function Find-PgTool([string]$name, [string]$given) {
    if ($given) { return $given }
    $candidate = Get-ChildItem "C:\Program Files\PostgreSQL\*\bin\$name.exe" -ErrorAction SilentlyContinue |
        Sort-Object FullName -Descending | Select-Object -First 1
    if ($candidate) { return $candidate.FullName }
    if (Get-Command $name -ErrorAction SilentlyContinue) { return $name }
    throw "$name 를 찾지 못했습니다. 경로를 매개변수로 지정하세요."
}
$PgRestoreExe = Find-PgTool 'pg_restore' $PgRestoreExe
$PsqlExe = Find-PgTool 'psql' $PsqlExe

$env:PGPASSWORD = $dbPw
try {
    $connect = @("--host=$dbHost", "--port=$dbPort", "--username=$dbUser")

    function Invoke-Sql([string]$db, [string]$sql) {
        $previous = $ErrorActionPreference
        $ErrorActionPreference = 'Continue'
        try {
            $out = & $PsqlExe @connect "--dbname=$db" '--tuples-only' '--no-align' '--command' $sql
            $code = $LASTEXITCODE
        } finally { $ErrorActionPreference = $previous }
        if ($code -ne 0) { throw "psql 실패 (exit $code): $sql" }
        return ($out -join "`n").Trim()
    }

    # --- 있는 DB 를 덮지 않는다 -----------------------------------------------
    $exists = Invoke-Sql 'postgres' "select 1 from pg_database where datname = '$DbName'"
    if ($exists -eq '1') {
        if (-not $Force) {
            throw @"
'$DbName' 이 이미 있습니다. 아무것도 하지 않았습니다.

복구는 대개 "옛 상태를 옆에 띄워 보는" 일입니다 — 살아 있는 DB 를 실수로 덮으면
되돌릴 데가 없습니다.

  옆에 띄워 보려면 :  -DbName ${DbName}_restore_check
  정말 덮으려면    :  -Force
"@
        }
        Write-Warning "'$DbName' 을 지우고 다시 만듭니다 (-Force)."
        # **접속을 먼저 끊는다.** 앱이 붙어 있으면 DROP 이 막히고, 그 오류는
        # "권한이 없다" 처럼 보인다.
        Invoke-Sql 'postgres' "select pg_terminate_backend(pid) from pg_stat_activity where datname = '$DbName' and pid <> pg_backend_pid()" | Out-Null
        Invoke-Sql 'postgres' "drop database ""$DbName""" | Out-Null
    }

    Write-Log "데이터베이스 만들기: $DbName"
    Invoke-Sql 'postgres' "create database ""$DbName""" | Out-Null

    # --- 되돌리기 --------------------------------------------------------------
    Write-Log 'pg_restore 실행'
    Invoke-Native $PgRestoreExe (@(
        "--host=$dbHost", "--port=$dbPort", "--username=$dbUser",
        "--dbname=$DbName", '--no-owner', '--no-privileges', $dumpPath
    )) 'pg_restore'

    $tables = Invoke-Sql $DbName "select count(*) from information_schema.tables where table_schema='public'"
    Write-Log "표 $tables 개"

    # --- 파일스토어 ------------------------------------------------------------
    $storeSource = Join-Path $BackupPath 'filestore'
    $storeTarget = $null
    if ($AppPath) {
        $storeTarget = Join-Path ($AppPath + '_data') 'filestore'
        if (Test-Path $storeSource) {
            Write-Log "파일스토어 되돌리기: $storeTarget"
            New-Item -ItemType Directory -Force -Path (Split-Path $storeTarget) | Out-Null
            # **지우고 넣지 않는다.** 백업에 없는 파일이 지금 있을 수 있고,
            # 그것을 지우는 판단은 이 스크립트가 할 것이 아니다.
            Copy-Item -Recurse -Force $storeSource $storeTarget
        } else {
            Write-Warning '백업에 파일스토어가 없습니다. DB 만 되돌렸습니다.'
        }
    } else {
        Write-Log 'AppPath 를 안 주셨습니다 — DB 만 되돌렸습니다(리허설).'
    }

    # --- 시점이 맞는가 ---------------------------------------------------------
    #
    # **여기가 이 스크립트의 절반이다.** DB 와 파일스토어가 다른 시점의 것이면
    # 「DB에는 있는데 파일이 없는」 행이 생기고, 그 상태로 앱이 뜬다 — 화면은
    # 멀쩡하고 그 곡선을 열 때만 터진다.
    $checkRoot = if ($storeTarget -and (Test-Path $storeTarget)) { $storeTarget }
                 elseif (Test-Path $storeSource) { $storeSource }
                 else { $null }

    $missing = 0
    $checked = 0
    if ($checkRoot) {
        Write-Log '가리키는 파일이 있는지 확인'
        # **파일을 가리키는 컬럼을 여기 적지 않는다.** 적어 두면 새 표가
        # 붙을 때 이 목록에 더하는 것을 잊고, 그러면 검사가 조용히 그 표를
        # 건너뛴다 — 검사가 있는데 안 보는 상태가 가장 나쁘다.
        #
        # 실제로 그랬다: 처음에 `test_runs.storage_path` 라고 적었는데 그 표의
        # 컬럼 이름은 `source_path` 였고, `curves`·`master_curves` 는 아예
        # 빠져 있었다. 카탈로그에 물어보면 그런 일이 안 생긴다.
        $columns = Invoke-Sql $DbName @'
select table_name || '.' || column_name
from information_schema.columns
where table_schema = 'public'
  and column_name in ('storage_path', 'source_path')
order by 1
'@
        $paths = @()
        foreach ($pair in ($columns -split "`n")) {
            $trimmedPair = $pair.Trim()
            if (-not $trimmedPair) { continue }
            $table, $column = $trimmedPair -split '\.', 2
            $found = Invoke-Sql $DbName "select $column from ""$table"" where $column is not null"
            if ($found) { $paths += ($found -split "`n") }
        }
        foreach ($relative in $paths) {
            $trimmed = $relative.Trim()
            if (-not $trimmed) { continue }
            $checked++
            if (-not (Test-Path (Join-Path $checkRoot $trimmed))) { $missing++ }
        }
    }

    Write-Host ''
    if ($checked -eq 0 -and $checkRoot) {
        # **0개를 "전부 있다" 로 적으면 안 된다.** 가리키는 파일이 없는 것과
        # 검사가 아무것도 못 찾은 것은 다르고, 뒤엣것은 검사가 고장난 것이다.
        Write-Warning 'DB 가 가리키는 파일이 하나도 없습니다 — 빈 백업이거나 검사가 표를 못 찾았습니다.'
    }
    if ($null -eq $checkRoot) {
        Write-Warning '파일스토어를 안 봤습니다 — DB 만 되돌린 상태입니다.'
    } elseif ($missing -gt 0) {
        Write-Host ''
        throw @"
DB 가 가리키는 파일 $missing 개가 없습니다 (확인한 것 $checked 개).

**DB 와 파일스토어의 시점이 어긋났습니다.** 이 상태로 앱을 띄우면 화면은
멀쩡하고 그 곡선을 열 때만 터집니다. 같은 백업 폴더의 filestore\ 를 함께
되돌리세요.
"@
    } else {
        Write-Log "가리키는 파일 $checked 개가 전부 있습니다."
    }

    Write-Host ''
    Write-Log "복구 완료: $DbName (표 $tables 개, 파일 $checked 개 확인)"
    if (-not $AppPath) {
        Write-Host ''
        Write-Host '  리허설이었습니다. 이 DB 는 앱이 안 씁니다 — 확인이 끝나면 지우세요:'
        Write-Host "    dropdb --host=$dbHost --port=$dbPort --username=$dbUser $DbName"
    }
    Write-Host ''
} finally {
    $env:PGPASSWORD = ''
}
