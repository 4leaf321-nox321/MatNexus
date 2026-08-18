<#
직전 버전으로 되돌린다.

**파일만 되돌아간다. 마이그레이션은 취소되지 않는다.** 실패한 배포가 파괴적
마이그레이션(컬럼 삭제·이름 변경)을 적용했다면 데이터베이스는 따로 복구해야 한다.

되돌린 버전의 requirements.txt 가 다르면 가상환경이 새 버전 기준으로 남아 있다.
그때는 `venv_sync.ps1 -Force` 를 한 번 실행한다.

롤백 전에 앱을 중지한다 — 윈도우는 실행 중인 파일을 잠근다.

사용:
  .\rollback.ps1 -AppPath 'C:\Server\MatNexus'
#>

param(
    [Parameter(Mandatory = $true)][string]$AppPath
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
function Write-Log([string]$m) { Write-Host "[$(Get-Date -Format 'HH:mm:ss')] $m" }

$prevPath = $AppPath + '_prev'
$tempPath = $AppPath + '_rollback_tmp'

if (-not (Test-Path $prevPath)) { throw "직전 버전이 없습니다: $prevPath" }
if (-not (Test-Path $AppPath)) { throw "현재 설치가 없습니다: $AppPath" }

# 잠금 확인은 실제로 할 연산(이름 바꾸기)으로 한다. 루트에 파일을 써 보는 것은
# 하위 폴더(backend)에 머문 프로세스를 잡아내지 못한다 — deploy.ps1 주석 참조.
if (Test-Path $tempPath) { Remove-Item -Recurse -Force $tempPath }
try {
    [System.IO.Directory]::Move($AppPath, $tempPath)
} catch {
    throw "$AppPath 를 옮길 수 없습니다. 실행 중인 앱과 그 폴더(하위 폴더 포함)에 들어가 있는 창을 닫고 다시 시도하세요."
}

# 제3의 이름을 거쳐 교환한다. 중간에 실패해도 두 이름이 같은 내용을 가리키거나
# 운영 경로가 사라지는 상태가 되지 않는다. Directory.Move 는 원자적 이름 변경이라
# 부분 이동이 생기지 않는다.
Write-Log '현재 버전과 직전 버전 교환'
try {
    [System.IO.Directory]::Move($prevPath, $AppPath)
} catch {
    # 되돌린다 — 운영 경로가 비어 있는 상태로 끝나지 않게.
    [System.IO.Directory]::Move($tempPath, $AppPath)
    throw "직전 버전을 옮기지 못했습니다: $_"
}
[System.IO.Directory]::Move($tempPath, $prevPath)

Write-Log '롤백 완료'
Write-Host ''
Write-Host '시작:'
Write-Host "  cd '$AppPath'"
Write-Host '  .\run_server.ps1'
Write-Host ''
Write-Host "되돌린 버전은 이제 $prevPath 에 있습니다."
Write-Host '데이터베이스 마이그레이션은 되돌아가지 않았습니다.'
