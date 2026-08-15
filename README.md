# MatNexus

물성 관리 시스템. 시험 데이터를 등록하고, 전후처리해서 탄소성·점탄성 등의 물성으로
만들고, 통계 처리하고, 시뮬레이션 툴 입력으로 내보낸다. 장비 데이터 자동 수집
파이프라인까지 확장한다.

- 계획: [docs/개발계획.md](docs/개발계획.md) — **§0 진행 현황**에 재개 지점이 있다
- 결정 기록: [docs/adr/](docs/adr/)
- 현재 상태: **Phase 0·1 완료, 서버 배포 완료(v0.1.4). 다음은 Phase 2(시험 데이터 등록).**

운영 서버는 **창 두 개**로 돈다 — `run_server.ps1`(API·화면)과 `run_worker.ps1`(알림·
비동기 작업). 워커가 없으면 작업이 큐에 쌓이기만 하고 알림이 가지 않는다.

## 구성

| 경로 | 내용 |
|---|---|
| `backend/app/` | FastAPI 앱. 모듈 2계층(`models`/`routes`/`schemas`/`services`) |
| `backend/matcore/` | 순수 계산 커널. DB·HTTP를 모른다 (`tests/architecture`가 검사) |
| `backend/definitions/` | 시험종류·채널·단위·검증규칙의 단일 소스 (Phase 2) |
| `frontend/src/modules/` | 백엔드 모듈과 **같은 이름**을 쓴다 (개발계획 §4.2) |
| `frontend/src/shared/` | 레이아웃·UI 프리미티브·API 클라이언트 |
| `scripts/` | 윈도우 설치·배포 스크립트 (Phase 0-4) |

## 개발 환경

- Python **3.12** (`py -3.12`) — wheel ABI가 배포 서버와 일치해야 한다
- Node 20+
- PostgreSQL 17

### 포트

| | 포트 | 비고 |
|---|---|---|
| 백엔드 | **8010** | 5173·5174·3000~3010은 같은 PC의 다른 플랫폼이 쓴다 |
| 프론트(개발) | **5190** | `strictPort` — 밀려서 다른 포트로 뜨지 않게 |

### 실행

```powershell
# 백엔드 (최초 1회)
cd backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
copy .env.example .env      # DATABASE_URL 수정
.\.venv\Scripts\alembic.exe upgrade head
.\.venv\Scripts\python.exe scripts\seed_install.py   # 초기 관리자 — 비밀번호가 1회 출력된다

# 백엔드 실행
.\.venv\Scripts\python.exe run.py

# 프론트엔드 (별도 창)
cd frontend
npm install
npm run dev
```

개발 중에는 프론트(5190)가 `/api`를 백엔드(8010)로 프록시한다. 배포에서는 백엔드
한 프로세스가 API와 SPA를 함께 서빙하므로, 프론트 코드는 **API 절대주소를 갖지
않는다**.

### 검증

```powershell
cd backend
.\.venv\Scripts\ruff.exe format .       # 포맷 (line-length 95)
.\.venv\Scripts\ruff.exe check .        # 린트
.\.venv\Scripts\mypy.exe                # 타입 (strict)
.\.venv\Scripts\python.exe -m pytest    # 단위·API·경계 테스트

cd ..\frontend
npm run build                            # tsc -b + vite build
```

### API 스키마가 바뀌었을 때

프론트 타입은 **손으로 적지 않는다.** 백엔드 스키마에서 생성한다(개발계획 D13).
`pytest` 의 `test_openapi_baseline_is_current` 가 이 두 단계를 빠뜨렸는지 검사한다.

```powershell
cd backend
.\.venv\Scripts\python.exe scripts\export_openapi.py   # openapi.json 갱신
cd ..\frontend
npm run api:types                                       # schema.d.ts 재생성
```

사용법:

```ts
import type { components } from '@/shared/api/schema'
type LoginResponse = components['schemas']['LoginResponse']
```

## 배포

상세는 [ADR 0003](docs/adr/0003-윈도우-배포-방식.md). 릴리스 자산
`deploy_package.zip` 하나에 코드·SPA·wheel 번들·배포 스크립트가 모두 들어 있다.

```powershell
# 최초 1회 — 릴리스에서 배포 스크립트를 꺼낸다
gh release download --repo 4leaf321-nox321/MatNexus --pattern deploy_package.zip
Expand-Archive .\deploy_package.zip .\unpacked
New-Item -ItemType Directory -Force -Path 'C:\Server\tools\MatNexus'
Copy-Item .\unpacked\install.ps1, .\unpacked\precheck.ps1, .\unpacked\deploy.ps1,
          .\unpacked\rollback.ps1 'C:\Server\tools\MatNexus\'

cd C:\Server\tools\MatNexus
.\precheck.ps1 -AppPath 'C:\Server\MatNexus' -DatabaseUrl 'postgresql+psycopg://postgres:<암호>@localhost:5432/matnexus'
.\install.ps1  -AppPath 'C:\Server\MatNexus' -DbPassword '<암호>'

# 갱신 — 앱을 먼저 중지할 것
.\deploy.ps1   -AppPath 'C:\Server\MatNexus'
.\rollback.ps1 -AppPath 'C:\Server\MatNexus'
```

### 백업

**DB와 파일스토어를 같은 시각에 함께 받는다.** DB에는 곡선의 경로와 해시가,
파일스토어에는 그 내용이 있어서 한쪽만 되돌리면 "DB에는 있는데 파일이 없는" 행이
생긴다.

```powershell
cd C:\Server\tools\MatNexus
.\backup.ps1 -AppPath 'C:\Server\MatNexus' -BackupRoot 'D:\backup\matnexus' -KeepDays 30
```

받은 폴더의 `MANIFEST.txt` 에 복구 절차가 함께 적혀 있다. **한 번은 실제로 복구해
보라** — 받아만 두고 복구해 본 적 없는 백업은 백업이 아니다. 65도 RA도 이 절차
자체가 없었다.

정기 실행은 작업 스케줄러에 등록한다(반입물 없음).

### 관리자 계정

로그인 아이디는 **이메일 형식이 아니어도 된다** (`admin` 같은 짧은 아이디 허용).
비밀번호를 잊었거나 아이디를 바꿔야 하면 서버 콘솔에서 고친다.

```powershell
cd C:\Server\MatNexus\backend
$py = 'C:\Server\MatNexus_venvs\backend\Scripts\python.exe'

& $py scripts\set_admin.py --email admin --password '...'                    # 비밀번호 재설정
& $py scripts\set_admin.py --email admin --password '...' --rename-from old@x # 아이디 변경
& $py scripts\set_admin.py --email admin --password '...' --no-force-change   # 강제 변경 끄기
```

`--no-force-change` 는 파일럿·개발 편의용이다. 운영에서는 강제 변경을 켜 둔다 —
시드 비밀번호가 그대로 남는 것이 폐쇄망 설치에서 가장 흔한 사고다.

**스크립트를 `tools\MatNexus\` 하위에 둔다.** `C:\Server\tools` 바로 아래에 두면
같은 서버에 사는 다른 앱의 `deploy.ps1`·`rollback.ps1` 과 이름이 겹쳐 서로를
덮어쓴다(실측: 이 PC의 `C:\Server\tools` 에 이미 다른 프로젝트의 같은 이름
스크립트가 있었다).

폴더 배치:

```
C:\Server\MatNexus          코드 (배포마다 교체)
C:\Server\MatNexus_prev     직전 버전 (롤백용)
C:\Server\MatNexus_venvs    가상환경 (requirements 가 바뀔 때만 재생성)
C:\Server\MatNexus_data     filestore · logs ← 배포가 건드리지 않는다. 백업 대상
C:\Server\tools\MatNexus    배포 스크립트 (앱 폴더 바깥, 프로젝트별로 분리)
```

**`.ps1` 파일은 UTF-8 BOM 으로 저장해야 한다.** Windows PowerShell 5.1 이 BOM 없는
스크립트를 CP949 로 읽어 한글이 깨지고 구문 오류가 난다.
`tests/architecture/test_scripts_encoding.py` 가 이를 검사한다. 편집기가 BOM 을
떼어냈다면:

```powershell
$bom = New-Object System.Text.UTF8Encoding $true
$text = [System.IO.File]::ReadAllText($path, (New-Object System.Text.UTF8Encoding $false))
[System.IO.File]::WriteAllText($path, $text, $bom)
```

## 개발 중 걸려 넘어지기 쉬운 것

**접속 주소가 백엔드와 프론트가 다르다.** 백엔드는 `0.0.0.0`(IPv4)에 바인딩하므로
윈도우에서 `localhost`(::1로 먼저 해석)로는 연결이 거부된다 — `127.0.0.1:8010`을
쓴다. 반대로 Vite는 `localhost`에 바인딩하므로 `localhost:5190`을 쓴다.

**리로드 자식 프로세스는 명령줄로 못 찾는다.** `run.py`는 개발 모드에서
`reload=True`로 뜨고, uvicorn이 띄우는 자식 프로세스의 명령줄은
`multiprocessing.spawn ...` 이라 `66_MatNexus` 문자열이 없다. 명령줄로 죽이면
자식이 살아남아 **옛 코드로 계속 서빙한다**(수정이 반영 안 된 것처럼 보인다).
실행 파일 경로로 찾는다.

```powershell
Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.ExecutablePath -like '*66_MatNexus*' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
```

**테스트는 개발 DB를 건드리지 않는다.** `matnexus_test` 를 따로 만들어 쓴다
(`tests/conftest.py`). 개발 데이터가 지워지는 테스트는 아무도 돌리지 않게 되고,
그러면 릴리스 게이트로 올릴 수도 없다 — RA의 CI화를 막은 원인이 정확히 그것이다.

**로그는 파일에도 남는다.** `backend/logs/app.log` (자정 로테이션). 오류 응답의
`request_id`로 로그를 검색하면 해당 요청의 모든 줄을 찾을 수 있다. PowerShell에서
읽을 때는 `-Encoding UTF8`을 붙인다(기본 ANSI로 읽으면 한글이 깨진다).
