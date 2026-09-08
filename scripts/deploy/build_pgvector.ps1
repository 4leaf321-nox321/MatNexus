<#
pgvector 빌드 — **개발 PC 에서 한 번, 산출물 세 개를 뽑는다.**

윈도우 PostgreSQL 에는 pgvector 가 안 들어 있고, 공식 윈도우 바이너리도 없다.
소스 확장이라 직접 빌드해야 하는데 — **운영 서버에 Visual Studio 를 깔 이유는
없다.** 여기서 뽑은 세 파일을 서버에 복사하면 끝난다(`install_pgvector.ps1`).

    vector.dll              → <PG>\lib\
    vector.control          → <PG>\share\extension\
    vector--<판>.sql        → <PG>\share\extension\

**PostgreSQL 메이저 판마다 따로 빌드해야 한다.** 17 용 DLL 은 16 에서 안 뜬다 —
서버 API 가 메이저마다 바뀌기 때문이다. 그래서 산출물 폴더 이름에 판을 박는다.

## 실측한 함정 (2026-09-08)

VS 2019 Build Tools + 최신 Windows SDK(10.0.26100) 로 빌드하면 **링크에서 죽는다**:

    libucrt.lib(checkcfg.obj) : error LNK2001:
        확인할 수 없는 외부 기호 _guard_check_icall_$fo$

새 SDK 의 UCRT 가 최신 링커만 아는 기호를 참조한다. `/guard:cf` 를 더해도 안 된다.
**SDK 를 10.0.19041 로 내리면 그대로 빌드된다** — 이 스크립트가 자동으로 그렇게
물러선다. 컴파일은 다 되고 마지막 링크에서만 죽어서, 모르면 소스를 의심하게 된다.

사용:
  .\build_pgvector.ps1
  .\build_pgvector.ps1 -Version v0.8.0 -PgRoot 'C:\Program Files\PostgreSQL\17'
#>

param(
    [string]$Version = 'v0.8.0',
    [string]$PgRoot,
    [string]$OutDir,
    [string]$WorkDir = (Join-Path $env:TEMP 'pgvector-build')
)

$ErrorActionPreference = 'Stop'
$repo = 'https://github.com/pgvector/pgvector.git'
#: 새 SDK 가 링크를 깨뜨릴 때 물러설 자리. 위에서부터 시도한다.
$sdkFallbacks = @('', '10.0.22621.0', '10.0.19041.0')

function Write-Log([string]$m) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $m" }

# 5.1 은 네이티브 명령이 stderr 에 한 줄만 내도 종료성 오류로 바꾼다. git clone 이
# 분리 HEAD 안내를 stderr 로 내므로, 감싸지 않으면 **성공한 클론에서 죽는다**
# (실측 2026-09-08). 종료 코드로 본다.
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
if (-not (Test-Path (Join-Path $PgRoot 'lib\postgres.lib'))) {
    throw "$PgRoot 에 lib\postgres.lib 가 없습니다. **서버 개발 파일**이 설치돼 있어야 합니다(설치 프로그램의 'Development' 구성 요소)."
}
$major = Split-Path $PgRoot -Leaf
Write-Log "PostgreSQL: $PgRoot (메이저 $major)"

if (-not $OutDir) {
    $OutDir = Join-Path (Split-Path $PSScriptRoot -Parent) "..\build\pgvector\pg$major"
}
$OutDir = [System.IO.Path]::GetFullPath($OutDir)

# --- 빌드 도구 찾기 ----------------------------------------------------------
$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
if (-not (Test-Path $vswhere)) {
    throw 'Visual Studio Build Tools 가 없습니다. "C++를 사용한 데스크톱 개발" 워크로드를 설치하세요 — https://aka.ms/vs/17/release/vs_BuildTools.exe'
}
# 최신 것부터 본다. PostgreSQL 자신이 VS2022 로 빌드돼 있어 그쪽이 잘 맞는다.
$installs = & $vswhere -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -sort -property installationPath
if (-not $installs) { throw 'C++ 빌드 도구(VC Tools)가 설치된 Visual Studio 를 못 찾았습니다.' }
$vcvars = $null
foreach ($one in @($installs)) {
    $candidate = Join-Path $one 'VC\Auxiliary\Build\vcvars64.bat'
    if (Test-Path $candidate) { $vcvars = $candidate; break }
}
if (-not $vcvars) { throw 'vcvars64.bat 을 못 찾았습니다.' }
Write-Log "빌드 도구: $vcvars"

# --- 소스 ---------------------------------------------------------------------
if (Test-Path $WorkDir) { Remove-Item -Recurse -Force $WorkDir }
Write-Log "소스를 받습니다: $Version"
Invoke-Native "소스를 받지 못했습니다($Version)" {
    & git -c advice.detachedHead=false clone --quiet --branch $Version --depth 1 $repo $WorkDir
}
if (-not (Test-Path (Join-Path $WorkDir 'Makefile.win'))) { throw "소스를 받지 못했습니다: $repo ($Version)" }

# --- 빌드 (막히면 SDK 를 내려 가며 다시) --------------------------------------
$built = $false
foreach ($sdk in $sdkFallbacks) {
    $label = if ($sdk) { "SDK $sdk" } else { '기본 SDK' }
    Write-Log "빌드 시도 — $label"
    $output = cmd /c "call `"$vcvars`" $sdk >nul 2>&1 && set `"PGROOT=$PgRoot`" && cd /d `"$WorkDir`" && nmake /F Makefile.win 2>&1"
    if (Test-Path (Join-Path $WorkDir 'vector.dll')) {
        Write-Log "빌드 성공 — $label"
        $built = $true
        break
    }
    $guard = $output | Select-String -SimpleMatch 'guard_check_icall'
    if ($guard) {
        Write-Log '  → 새 SDK 의 UCRT 가 링커와 안 맞습니다. 옛 SDK 로 물러섭니다.'
        # 다음 시도 전에 목적 파일을 치운다 — 섞이면 링크가 또 깨진다.
        Get-ChildItem (Join-Path $WorkDir 'src') -Filter *.obj | Remove-Item -Force
        continue
    }
    $output | Select-Object -Last 12 | ForEach-Object { Write-Host "    $_" }
    throw "빌드가 실패했습니다($label). 위 출력을 보세요."
}
if (-not $built) { throw '어느 SDK 로도 빌드하지 못했습니다.' }

# --- 산출물 -------------------------------------------------------------------
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Force $OutDir | Out-Null }
Copy-Item (Join-Path $WorkDir 'vector.dll') $OutDir -Force
Copy-Item (Join-Path $WorkDir 'vector.control') $OutDir -Force
Copy-Item (Join-Path $WorkDir 'sql\vector--*.sql') $OutDir -Force

# 어느 판으로 어디에 맞춰 빌드했는지 남긴다 — 나중에 「이 DLL 은 뭐지」 가 된다.
@{
    pgvector = $Version
    postgres_major = $major
    postgres_root = $PgRoot
    built_at = (Get-Date -Format 'yyyy-MM-dd HH:mm:ss')
    built_by = "$env:COMPUTERNAME\$env:USERNAME"
} | ConvertTo-Json | Set-Content (Join-Path $OutDir 'build-info.json') -Encoding utf8

Write-Host ''
Write-Log "산출물: $OutDir"
Get-ChildItem $OutDir | ForEach-Object { Write-Host ("    {0,-28} {1,8:N0} bytes" -f $_.Name, $_.Length) }
Write-Host ''
Write-Log '서버에 넣으려면 (관리자 PowerShell):'
Write-Host "    .\install_pgvector.ps1 -FromDir '$OutDir'"
Write-Host ''
