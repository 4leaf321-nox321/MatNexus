# 개발 지침

이 저장소에서 코드를 고칠 때 지키는 규칙. 배경과 근거는
[docs/개발계획.md](docs/개발계획.md), 결정은 [docs/adr/](docs/adr/) 에 있다.

**이 파일이 정본이다.** `CLAUDE.md` 는 이 파일을 가리키기만 한다 — 두 벌로
두면 한쪽만 고쳐지고, 그때 사람마다 다른 규칙을 따르게 된다. `tests/architecture`
가 그것을 검사한다.

## 누가 무엇을 만지는가

세 사람이 함께 고친다. **소유는 사람이 아니라 경로에 붙는다** — 누가 어느 도구를
쓰는지와 무관하게 같은 규칙이다. 정본은 [CODEOWNERS](.github/CODEOWNERS) 이고,
사람이 읽을 설명은 [docs/협업.md](docs/협업.md) 에 있다.

| 경로 | 누구의 것 |
| --- | --- |
| `backend/extensions/**` | 물성 개발자 |
| 그 밖의 전부 | 플랫폼 개발자 |

**자기 경로 밖은 고치지 않는다.** 중심 코드에 무언가 필요하면 고치지 말고
backlog 에 적고 멈춘다 — 그 파일을 다른 사람이 같은 시간에 고치고 있다.

새 물성은 `backend/extensions/<이름>/` 하나로 끝나야 한다. 중심 코드에 이름을
적어야만 읽히면 그것은 확장이 아니다([extensions.py](backend/matcore/extensions.py)).
확장이 부를 수 있는 등록 함수는 넷이다 — `registry.register`(처리) ·
`cards.register_block` · `export.register_renderer` · `fitting.register_family`.

**릴리스는 플랫폼 개발자만 한다.** `frontend/package.json` 의 버전을 올리는 것이
곧 배포 결정이고([auto-tag.yml](.github/workflows/auto-tag.yml)), 그 파일은
릴리스마다 바뀌므로 여럿이 만지면 매번 충돌한다.

**확장은 마이그레이션을 쓰지 않는다.** `matcore` 와 `extensions` 는 DB 를 모른다 —
필요해지면 그 자체가 설계를 다시 볼 신호이므로 요청한다.

## 범위 — 좁게, 다만 예외가 있다

작업은 요청받은 범위 안에서 한다. **다만 기존 배치가 이 문서의 규칙과 어긋나면
작업 스코프 안에서 바로잡는다 — 단, 자기 소유 경로 안에서만.** 스코프를 넘거나
남의 경로에 걸치면 backlog 에 `구조 정리` 항목으로 남긴다.

이 예외 조항이 필요한 이유: 65는 지침이 *"change only the missing bounded scope"*
만 말하고 예외가 없어서, 새 기능을 **루트에 새 파일로 추가하는 것이 규율상 가장
안전한 선택**이 되었다. 436커밋이 쌓여 프론트가 122파일 평면이 됐다.

소유 경로 단서가 붙은 이유는 그 반대다. 예외를 그대로 두면 **남의 파일을 「규칙에
맞게」 고치는 것이 정당해진다** — 셋이 함께 고치는 저장소에서 그것은 충돌이다.

## 구조

- **`backend/matcore/` 는 DB도 HTTP도 모른다.** 이 설계의 전제 전부다.
  `sqlalchemy`·`fastapi`·`app.*` 를 import 하면 `tests/architecture` 가 막는다.
  새 계산은 `@register(...)` 로 등록한다 — 새 물성 추가가 파일 2~3개로 끝나야 한다.
- **모듈 이름은 백엔드와 프론트가 같다.** `app/modules/<name>` ↔
  `frontend/src/modules/<name>`. 예외는 `tests/architecture/test_boundaries.py` 의
  `FRONTEND_ONLY`·`BACKEND_ONLY` 에 사유와 함께 적는다.
- **모듈끼리 직접 부르지 않는다.** 예외는 `models` 뿐이다(FK 는 본질적으로 서로를
  참조한다). 로직 공유는 `shared` 를 거친다.
- **워크벤치는 조립만 한다.** 탭의 도메인 로직은 각 도메인 모듈에 산다.

## 데이터

- 새 ORM 모델을 만들면 **`app/all_models.py` 에 import 를 추가**한다. 빠뜨리면
  autogenerate 가 기존 테이블을 지우는 마이그레이션을 만든다. **DB 를 만지는
  스크립트도 `app.all_models` 를 import 한다** — 앱에서는 안 드러나고 배포 뒤
  그 스크립트를 돌릴 때만 터진다.
- 불변(곡선·처리결과·모델 파라미터·카드)과 가변(표시 설정·임계값·라벨)을 섞지
  않는다. 라벨 하나 바꿨다고 리비전이 찍히면 안 된다.
- 삭제·이관 기능을 만들기 전에 의존성 레지스트리(`shared/dependents.py`)를 먼저 둔다.
- 목록 엔드포인트에는 서버가 상한을 강제한다. N+1 은 명시적 join 으로 막는다.

## API

- 성공 응답은 리소스 그대로, 오류만 엔벨로프(ADR 0001). 오류 코드는
  `MNX-<MODULE>-<NNNN>`.
- **오류 본문을 라우트에서 직접 만들지 않는다.** `AppError` 계열을 raise 한다 —
  응답을 만드는 경로가 곧 로그를 남기는 경로여야 한다.
- **부분 수정을 받을 때는 「안 보낸 것」과 「비운 것」을 구별한다.** 안 구별하면
  그냥 저장할 때마다 값이 지워진다 — 선언 물성·일괄 수정·읽을 형식 셋이 같은
  자리에서 걸렸다.
- 스키마를 바꿨으면 `python scripts/export_openapi.py` 와 `npm run api:types` 를
  함께 돌린다. 프론트 타입을 손으로 적지 않는다. CI 가 검사한다.

## 프론트

- 스타일은 Tailwind 유틸리티로 컴포넌트에 붙인다. 전역 CSS 클래스를 새로 만들지
  않는다 — 65의 GUI 불안정 원인이 전역 이름공간 공유였다.
- API 절대주소를 코드에 넣지 않는다. 항상 상대경로 `/api`.
- shadcn 프리미티브 위에 도메인 콘텐츠 컴포넌트(테이블·필터 폼·곡선 차트)를 쌓고,
  화면은 조립만 한다.
- **단위·기호를 라벨에 손으로 적지 않는다.** 표(`shared/units.ts`)에서 읽는다 —
  표만 바꾸면 라벨은 옛 단위를 적은 채 새 값을 받는다.

## 스크립트

- `.ps1` 은 **UTF-8 BOM** 으로 저장한다. Windows PowerShell 5.1 이 BOM 없는
  스크립트를 CP949 로 읽어 한글이 깨지고 구문 오류가 난다. 편집 도구가 BOM 을
  떼면 README 의 복구 명령을 쓴다. 테스트가 검사한다.
- 네이티브 명령은 `Invoke-Native` 로 감싼다. 5.1 은 stderr 한 줄을 종료성 오류로
  바꾼다(alembic 은 INFO 를 stderr 로 낸다).

## 검증

고치고 나서 이 넷을 돌린다. CI 가 같은 것을 강제한다.

```powershell
cd backend
.\.venv\Scripts\ruff.exe format . ; .\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\mypy.exe
.\.venv\Scripts\python.exe -m pytest
cd ..\frontend ; npm run build
```

테스트는 `matnexus_test_gw0`~`_gw3` 을 쓴다(워커 4개로 나눠 돈다). 개발 DB를
건드리는 테스트는 쓰지 않는다.

**스위트를 둘 동시에 돌리지 않는다.** 워커별로 나눈 것은 **한 실행 안에서**다 —
`pytest` 를 두 번 띄우면 둘 다 `_gw0` 을 쓰므로 서로의 데이터를 지운다. 증상이
나면 코드보다 먼저 살아 있는 pytest 프로세스를 본다 —
`Get-CimInstance Win32_Process -Filter "Name='python.exe'" | Where-Object { $_.CommandLine -like '*pytest*' }`.

**전체 스위트는 커밋 직전 한 번만 돌린다.** 개발 중에는 건드린 파일만 돌린다
(`pytest tests/unit/test_x.py`, 10초 안쪽). 전체는 102초이고, 습관적으로 여러 번
돌리면 그것만으로 하루가 간다.

**사보타주는 등급을 매긴다.** 고친 코드를 일부러 망가뜨려 시험이 무는지 보는
것은 값지지만 비싸다. **되돌릴 수 없거나 조용히 틀리는 것**에만 한다 — 삭제·병합·
단위 환산·권한·이관. 화면 문구·레이아웃·목록 표시는 시험만 쓰고 넘어간다.

**프론트는 `npx vitest` 를 배경에 띄워 둔다.** 한 파일만 돌려도 콜드 스타트가
21초라 좁혀 돌리는 이득이 거의 없다(전체가 55초다). 지켜보기로 띄워 두면 바뀐
파일만 0.5초에 다시 돈다.

## 문서

- 판단이 갈렸던 결정은 `docs/adr/NNNN-제목.md` 에 남긴다 — 결정·배경·대안·결과.
- 실측으로 드러난 함정은 근거(무엇을 관측했는지)와 함께 적는다. "이렇게 하세요"
  보다 "이렇게 안 하면 이런 일이 났다"가 다음 사람에게 유용하다.
