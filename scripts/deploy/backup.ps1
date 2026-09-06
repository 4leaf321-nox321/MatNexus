<#
백업 — 데이터베이스와 운영 데이터를 함께 받는다.

**둘 중 하나만 받으면 복구되지 않는다.** DB에는 곡선의 경로와 해시가, 파일스토어에는
그 곡선의 실제 내용이 있다(D10). 시점이 어긋나면 "DB에는 있는데 파일이 없는" 행이
생긴다. 그래서 한 스크립트가 같은 시각에 둘 다 받는다.

## 배치 (2026-09-05, 세대 정책)

    <BackupRoot>\db\db-<yyyyMMdd-HHmmss>.dump   pg_dump 커스텀 포맷 — 일 7벌 + 일요일분 4벌
    <BackupRoot>\filestore\                     시험 원본·Parquet·처리 결과 — robocopy 미러 1벌
    <BackupRoot>\env\.env                       접속 정보·JWT 비밀키 — 최신 1벌
    <BackupRoot>\LAST_BACKUP.txt                무엇을 언제 받았는지

전에는 실행마다 `<타임스탬프>\` 폴더에 파일스토어를 통째로 복사했다. 파일스토어는
**불변 파일**(원본·Parquet 는 한 번 쓰고 안 바뀐다)이라 세대가 필요 없고, 통째로
복사하면 디스크를 세대 수만큼 먹는다 — 미러 한 벌이면 된다. DB 덤프만 세대를 둔다.

## 작업 스케줄러 (사람이 한 번 등록한다)

워커 프로세스에 넣지 않는다 — 워커가 죽은 날 백업도 조용히 죽는다.

    $action  = New-ScheduledTaskAction -Execute 'powershell.exe' `
      -Argument '-NoProfile -ExecutionPolicy Bypass -File C:\Server\tools\MatNexus\backup.ps1 -AppPath C:\Server\MatNexus -BackupRoot D:\MatNexus-backup'
    $trigger = New-ScheduledTaskTrigger -Daily -At 03:00
    Register-ScheduledTask -TaskName 'MatNexus Backup' -Action $action -Trigger $trigger -RunLevel Highest -User 'SYSTEM'

`backend\.env` 에 `BACKUP_DIR=D:\MatNexus-backup` 을 적으면 서버 화면이 마지막 백업
시각을 보이고, 36시간이 지나면 붉게 말한다.

사용:
  .\backup.ps1 -AppPath 'C:\Server\MatNexus' -BackupRoot 'D:\MatNexus-backup'
  .\backup.ps1 -AppPath 'C:\Server\MatNexus' -BackupRoot 'D:\MatNexus-backup' -KeepDaily 14 -KeepWeekly 8
#>

param(
    [Parameter(Mandatory = $true)][string]$AppPath,
    [Parameter(Mandatory = $true)][string]$BackupRoot,
    [int]$KeepDaily = 7,
    [int]$KeepWeekly = 4,
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

<#
네이티브 명령을 감싼다. Windows PowerShell 5.1 은 네이티브 명령이 stderr 로 한 줄만
내도 그것을 종료성 오류로 바꾼다 — pg_dump 는 진행 상황을 stderr 로 낸다. 판정은
**종료 코드로만** 한다.
#>
function Invoke-Native([string]$exe, [string[]]$arguments, [string]$what, [int[]]$okCodes = @(0)) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        & $exe @arguments
        $code = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previous
    }
    if ($okCodes -notcontains $code) { throw "$what 실패 (exit $code)" }
    return $code
}

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
$dbDir = Join-Path $BackupRoot 'db'
$envDir = Join-Path $BackupRoot 'env'
$storeTarget = Join-Path $BackupRoot 'filestore'
foreach ($dir in @($BackupRoot, $dbDir, $envDir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
}

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
# **`.part` 로 쓰다가 끝나면 이름을 바꾼다.** 도중에 죽으면 반쪽 덤프가 `.dump` 로
# 남고, 서버 화면은 그것을 「마지막 백업」 으로 읽는다.
Write-Log "데이터베이스 백업: $dbName"
$dumpPath = Join-Path $dbDir "db-$stamp.dump"
$partPath = "$dumpPath.part"
$env:PGPASSWORD = $dbPw
try {
    Invoke-Native $PgDumpExe @("--host=$dbHost", "--port=$dbPort", "--username=$dbUser",
        '--format=custom', "--file=$partPath", $dbName) 'pg_dump' | Out-Null
} finally {
    $env:PGPASSWORD = ''
}
Move-Item -Force $partPath $dumpPath

# --- 운영 데이터: 미러 ------------------------------------------------------------
# robocopy 종료 코드는 비트 플래그다 — 0~7 이 성공(1 = 복사함, 2 = 여분 있음, 4 = 불일치),
# 8 이상이 실패. 5.1 이 stderr 를 오류로 바꾸는 것과 별개로 코드로 판정한다.
$storeSource = Join-Path $dataPath 'filestore'
$fileCount = 0
if (Test-Path $storeSource) {
    Write-Log "파일스토어 미러: $storeSource → $storeTarget"
    Invoke-Native 'robocopy.exe' @($storeSource, $storeTarget, '/MIR', '/R:2', '/W:5', '/NFL', '/NDL', '/NJH', '/NP') `
        'robocopy' @(0, 1, 2, 3, 4, 5, 6, 7) | Out-Null
    $fileCount = (Get-ChildItem $storeTarget -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count
} else {
    Write-Warning "파일스토어가 없습니다 ($storeSource). 아직 시험 데이터가 없다면 정상입니다."
}

Copy-Item -Force $envFile (Join-Path $envDir '.env')

# --- 세대 정리: 일 N벌 + 일요일분 M벌 ---------------------------------------------
# 안 지우면 백업이 디스크를 채운다. 파일 이름의 시각으로 판정한다(mtime 은 복사하면 바뀐다).
$dumps = Get-ChildItem $dbDir -Filter 'db-*.dump' | ForEach-Object {
    if ($_.Name -match '^db-(\d{8})-(\d{6})\.dump$') {
        [pscustomobject]@{ File = $_; At = [datetime]::ParseExact($Matches[1] + $Matches[2], 'yyyyMMddHHmmss', $null) }
    }
} | Sort-Object At -Descending
$daily = @($dumps | Select-Object -First $KeepDaily)
$weekly = @($dumps | Where-Object { $_.At.DayOfWeek -eq 'Sunday' } |
    Group-Object { $_.At.ToString('yyyy-MM-dd') } | ForEach-Object { $_.Group | Select-Object -First 1 } |
    Sort-Object At -Descending | Select-Object -First $KeepWeekly)
$keep = @($daily + $weekly | ForEach-Object { $_.File.FullName } | Sort-Object -Unique)
foreach ($dump in $dumps) {
    if ($keep -notcontains $dump.File.FullName) {
        Write-Log "오래된 덤프 삭제: $($dump.File.Name)"
        Remove-Item -Force $dump.File.FullName
    }
}
Get-ChildItem $dbDir -Filter '*.part' -ErrorAction SilentlyContinue | Remove-Item -Force

# --- 기록 --------------------------------------------------------------------
$dumpMb = [math]::Round((Get-Item $dumpPath).Length / 1MB, 1)
@(
    "받은 시각   : $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')",
    "앱 경로     : $AppPath",
    "데이터베이스: $dbName @ ${dbHost}:${dbPort}  ($(Split-Path $dumpPath -Leaf), ${dumpMb}MB)",
    "파일스토어  : $fileCount 개 파일 (미러: $storeTarget)",
    "보관        : 일 ${KeepDaily}벌 + 일요일분 ${KeepWeekly}벌 (덤프 $($keep.Count)개 남음)",
    '',
    '복구 방법:',
    "  .\restore.ps1 -BackupRoot '$BackupRoot' -DbName matnexus_restore_check          # 확인만",
    "  .\restore.ps1 -BackupRoot '$BackupRoot' -DbName $dbName -AppPath '$AppPath' -Force  # 실제 복구",
    '',
    '주의: DB 와 파일스토어는 같은 시점의 것이어야 한다. 파일스토어는 미러 한 벌이라',
    '      옛 덤프로 되돌리면 그 뒤에 올린 파일이 「DB 에는 없는데 파일은 있는」 상태가',
    '      된다 — 그것은 무해하다(저장소 정리가 오펀으로 잡는다). 반대는 없다.'
) | Set-Content -Path (Join-Path $BackupRoot 'LAST_BACKUP.txt') -Encoding utf8

Write-Log "백업 완료: $dumpPath (DB ${dumpMb}MB, 파일 $fileCount 개)"
Write-Host ''
Write-Host '  복구 절차는 LAST_BACKUP.txt 와 docs/운영-핸드북.md 에 있습니다.'
Write-Host '  **한 번은 실제로 복구해 보세요.** 받아만 두고 복구를 해 본 적이 없는 백업은'
Write-Host '  백업이 아닙니다.'
Write-Host ''
