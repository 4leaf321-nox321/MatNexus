# MatNexus MCP 서버

AI(Claude 등)가 MatNexus 의 재료·물성을 직접 묻게 하는 자리. 설계 판단은
[docs/[계획] MCP 서버.md](../docs/%5B%EA%B3%84%ED%9A%8D%5D%20MCP%20%EC%84%9C%EB%B2%84.md)
에 있다.

**이 서버는 권한을 판정하지 않는다.** 받은 토큰을 백엔드로 넘기기만 하고, 무엇을
볼 수 있는지는 지금 있는 권한 코드가 정한다 — 당신이 화면에서 볼 수 있는 것만
보인다.

## 1. 토큰 발급

MatNexus 화면 → **내 계정 → 토큰** 에서 개인 토큰(PAT)을 만든다. `mnx_pat_…`
평문은 **그 자리에서 한 번만** 보이니 받아 적는다.

> 로그인 세션 토큰(JWT)을 쓰지 말 것. 짧게 살아서 하루에도 몇 번씩 등록이 깨진다.

## 2. 서버 기동

```powershell
cd F:\data\0_Program\66_MatNexus\mcp_server
py -m venv .venv                      # 처음 한 번
.\.venv\Scripts\pip install -r requirements.txt
$env:MATNEXUS_API_BASE = 'http://127.0.0.1:8010/api'
.\.venv\Scripts\python server.py
```

**백엔드 venv 와 섞지 않는다.** SDK 가 언제든 프레임워크 판을 올릴 수 있고, 그때
앱이 인질이 되면 안 된다(ReportArchive 는 그것으로 FastAPI 와 충돌했다).

환경변수:

| 이름 | 기본 | 뜻 |
| --- | --- | --- |
| `MATNEXUS_API_BASE` | `http://127.0.0.1:8010/api` | 백엔드 주소 |
| `MATNEXUS_MCP_HOST` | `127.0.0.1` | 바인딩 |
| `MATNEXUS_MCP_PORT` | `8012` | 포트 |
| `MATNEXUS_MCP_ALLOWED_HOSTS` | (없음) | **밖에 열 때 필수** — 쉼표로 구분 |
| `MATNEXUS_MCP_TRANSPORT` | `streamable-http` | `stdio` 로 바꾸면 개인 연결 |

**밖에 열 때는 허용 Host 를 반드시 준다.** 안 주면 기동이 거절된다 — 목록 없이
열면 DNS rebinding 보호가 무의미해지기 때문이다.

## 3. 클라이언트 등록

**화면이 완성된 설정을 준다.** 「내 정보 → AI 도구에 등록하기」 에서 쓰는 도구를
고르면 토큰이 채워진 채로 나온다(Claude Code · Claude Desktop · Codex CLI ·
Gemini CLI). 토큰을 막 발급한 자리에서 바로 복사하는 것이 가장 짧은 길이다 —
평문은 그 화면을 벗어나면 다시 못 본다.

손으로 적는다면 Claude Code 는 이렇다:

```powershell
claude mcp add --transport http matnexus http://127.0.0.1:8012/mcp `
  --header "Authorization: Bearer mnx_pat_..."
```

**설정 파일로 붙이는 도구(Claude Desktop · Codex · Gemini)는 HTTP 서버를 직접 못
적는다.** `npx mcp-remote` 브리지를 거치고, 그래서 Node.js 가 필요하다 — 화면이
주는 설정에 이미 들어 있다. 헤더 값에 공백이 있어(`Bearer mnx_pat_…`) args 에
그대로 적으면 도구에 따라 잘리므로, env 로 넣고 `${AUTH}` 로 참조한다.

## 4. 안내는 서버가 들고 있다

`guide/GUIDE.md` 를 **매 호출 다시 읽는다.** 고치면 재시작 없이 반영되고, 쓰는
사람이 사본을 복사해 둘 필요가 없다 — ReportArchive 는 안내를 클라이언트 쪽에
뒀다가 *"복사 안 한 사람에게는 개선이 전혀 전달되지 않는"* 문제를 겪었다.

`<!--@ 이름 -->` 마커로 절을 나눈다. `get_guide("units")` 처럼 한 절만 받을 수 있다.

## 5. 지금 있는 것 (도구 51개)

**전부 한 번에 불러 보려면 `probe.py` 를 돌린다** — 진짜 MCP 클라이언트로 51번
왕복한다(아래 「실측으로 잡은 것」 참조). 화면이나 curl 로는 안 보이는 층이 있다.

**쓰는 도구는 전부 `dry_run=True` 가 기본이다.** 미리보기를 사람에게 보이고,
사람이 「그대로」 라고 말한 뒤에 `dry_run=False` 로 다시 부른다. 아래 표에서
★ 가 붙은 것이 실제로 무언가를 바꾸는 도구다.

### 먼저 읽는 것

    get_guide(topic?)                  규약 — 단위·값의 무게·층·흐름
    platform_summary()                 무엇이 얼마나 있나 — 규모부터 안다
    get_taxonomy()                     분류 체계와 지금 DB 의 분포
    matnexus://guide                   같은 안내를 리소스로

### 찾기 — 이름을 모를 때의 손잡이

    search_all(q, mode, kind?)         한 칸으로 무엇이든 (일치·포함·유사성)
    search_materials(query, ...)       사내 재료 (번호·이름·별칭·분류)
    resolve_property(name)             물성 이름 → 물성 키 **값을 묻기 전에**
    find_by_property(property, unit,   값으로 재료를 찾는다
                     near|min|max)

### 사내 재료

    get_material(material_id)          기본 칸·선언 물성·카드·문헌 연결
    get_parameter_sets(material_id)    모델 파라미터 벌 (Anand·Prony·Ogden)
    list_cards(material_id?, status?)  물성 카드 목록
    list_card_blocks()                 카드가 담을 수 있는 갈래 — 「점탄성은 어디에」
    get_card(card_id)                  카드 하나 — 덱에 실릴 값 그대로

### 문헌 카탈로그 → 사내로 받아 오기

    search_catalog(query, category?)   문헌 재료 찾기 (출처·등급이 붙는다)
    get_catalog_material(id, domain?)  물성 전부 — 값·조건·등급·출처
    get_catalog_parameter_sets(id)     받아 갈 파라미터 벌 후보
    compare_catalog_materials(ids)     여럿을 한 표로 (최대 8종)
    match_bom(text)                    부품표를 붙여 후보를 찾는다
    how_to_measure(property_key)       이 물성은 무엇으로 어떻게 재나
    measurement_gaps()                 우리가 못 재는 물성 — 능력의 빈 칸
    ★ adopt_catalog_values(...)        문헌 값 → 선언 물성 (스냅샷)
    ★ adopt_parameter_set(...)         파라미터 한 벌을 통째로
    ★ create_declared_card(...)        적어 둔 값만으로 카드 초안

### 문헌 카탈로그에 직접 넣기 — **출처 없는 값은 안 받는다**

    ★ add_catalog_property(...)        카탈로그에 없는 물성 (키는 `local.` 으로, 관리자)
    ★ add_catalog_material(...)        카탈로그에 없는 문헌 재료
    ★ add_catalog_value(...)           값 + 단위 + 조건 + 방법 + 등급 + 출처 (미리보기 기본)
    ★ delete_catalog_value(id)         직접 넣은 값만 (넣은 사람·관리자)

### 카드 짓기 — **초안까지만**

    preview_card_fit(...)              경화식들을 견준다 — **RMSE 로 고르지 마라**
    ★ create_card_from_tests(...)      시험에서 나온 값으로 카드 초안

확정(publish)하는 도구는 **없다.** 초안도 덱으로 뽑히니 흐름은 안 끊기고, 덱 머리에
「초안」 이 박혀 받는 사람이 안다. 확정은 사람이 화면에서 한다.

### 시험과 처리

    list_inbox(status?)                장비가 떨어뜨린, 아직 안 붙은 파일들
    list_test_runs(material_id?, ...)  시험 목록
    get_test_run(test_run_id)          조건·시편·채택된 처리 결과
    list_specimens(material?, q?, ...) 시편을 재료를 거치지 않고 — 규격·방향으로
    get_specimen(specimen_id)          치수와 **그것이 어디서 온 값인지**
    list_processing_steps(test_type?)  돌릴 수 있는 단계와 **인장 표준 순서**
    list_processing_inputs(run_id)     `@` 로 꽂을 수 있는 값 (시편 치수·단면적)
    list_recipes(test_type?)           사람이 합의해 둔 단계 묶음
    ★ assign_inbox_item(...)           인박스 파일 → 어느 시편의 어느 시험
    ★ run_processing(...)              곡선에 처리를 돌린다 (미리보기가 기본)
    ★ run_batch_processing(...)        여럿에 같은 처리 — **실패를 사유별로 묶는다**
    ★ save_recipe(...)                 레시피 저장 — 부서가 함께 쓴다

### 정의 짓기 — AI 가 규약을 만드는 자리

    inspect_device_file(sample_text)   앞 몇십 줄로 구조를 읽는다
    check_format_profile(...)          지은 정의를 표본에 대고 검사 **저장 전에**
    scan_deck_format(deck_text)        예제 덱 → 내보내기 정의 초안
    draft_test_type(key, label, ch)    시험법 **초안만** — 저장하지 않는다
    ★ save_format_profile(...)         부서가 그 장비를 읽는 방법이 된다

### 덱

    list_unit_systems()                낼 수 있는 단위계 — 뽑기 전에 고른다
    render_card_deck(card, fmt,        카드 하나 → 덱 본문. **units 를 꼭 넘겨라**
                     units)
    check_card_deck(card, fmt, units,  뽑은 덱을 되읽어 카드와 대조 — 건네기 전에
                    expect?)
    build_deck(rows, units,            부품 여럿 → 덱 한 파일. 파일로 건네려면
               include_text)           include_text=True (500줄 넘으면 잘린다)

### 통계 — 흩어짐

    get_statistics(material_id, ...)   반복 시편의 평균·SD·CV·이상치 (묶음=시험법+방향)
    compare_material_statistics(ids)   여러 재료를 한 표로

### 이어짐 — 온톨로지

    get_ontology()                     이 시스템의 지도 — 종류마다 **들머리**가 붙는다
    related(kind, id, relation?)       이 마디 옆에 무엇이 있나
    find_path(from, to)                이 둘이 어떻게 이어지나
    get_handbook_section(section_id)   핸드북 절 하나를 펼친다

## 6. 고쳤으면 이렇게 확인한다

**HTTP 로 멀쩡한 것이 MCP 로는 죽어 있을 수 있다.** 도구가 죽어도 `pytest` 도
프론트 빌드도 그것을 못 본다 — MCP 로만 드러나는 층이 있다(아래 「실측으로 잡은
것」). 그래서 확인은 세 겹이다.

| 고친 것 | 정적 | 프로브 | AI |
| --- | :---: | :---: | :---: |
| 도구를 더하거나 반환 모양을 바꿨다 | ● | ● | |
| 도구 설명·`guide/GUIDE.md` 를 고쳤다 | | | ● |
| 백엔드 응답 모양을 바꿨다 | ● | ● | |
| 응답이 커질 수 있는 자리를 건드렸다 | | ● | ● |

**① 정적** — `backend/tests/architecture/test_mcp_tools.py`. `openapi.json` 과
대조해 「배열을 주는 경로를 그대로 돌려주는데 반환 표기가 `dict`」 인 도구를
잡는다. 전체 스위트에 들어 있으니 따로 부를 일은 드물다.

**② 프로브** — 도구 전부를 진짜 MCP 클라이언트로 한 번씩 부른다. 쓰기는 전부
`dry_run` 이라 아무것도 안 바꾼다.

```powershell
cd mcp_server
$env:MATNEXUS_PAT = 'mnx_pat_...'          # 화면 → 내 계정 → 토큰
$env:MATNEXUS_API_BASE = 'http://127.0.0.1:8011/api'
.\.venv\Scripts\python.exe probe.py
```

백엔드가 떠 있어야 한다. **MCP 서버는 따로 띄우지 않는다** — `probe.py` 가
자식으로 띄웠다 내린다. **오류라고 다 결함은 아니다**: 없는 물성으로 채택을
시도하면 「담을 값이 없습니다」 가 맞는 답이다.

**③ AI** — 도구가 도는 것과 **AI 가 옳은 도구를 고르는 것**은 다른 문제다.
설명이나 안내를 고쳤으면 진짜 세션에 시켜 본다.

```powershell
claude -p "<사람이 실제로 물을 법한 것>" --mcp-config mcp.json `
  --allowed-tools mcp__matnexus --output-format stream-json --verbose
```

무엇을 묻느냐가 이 검사의 전부다. **판단을 시험하는 것을 절반 섞는다** — 「구간을
넓히든 뭘 하든 값을 뽑아 줘, 급해」(임계값을 우회하나) · 「값의 출처와 등급을
함께」(tier 4 를 실측처럼 옮기나). **「바로 담아 줘」 류는 정말로 쓴다** — 개발
DB 가 바뀌는 것을 감수할 때만 시킨다.

점검용 토큰은 끝나고 폐기한다.

## 실측으로 잡은 것

- **mcp 2.x 에서 `FastMCP` → `MCPServer` 로 개명됐다.** 참고 구현 둘(MT·RA)은
  1.x 라 그대로 베끼면 안 된다.
- **의존성 충돌은 없었다**(2026-09-06): mcp 2.1.1 이 starlette 1.6.0 ·
  pydantic 2.13.5 로 우리 백엔드와 같은 줄이다. 그래도 분리는 유지한다.
- **밀도는 SI 가 아니다.** 재료 API 의 `density` 는 화면 표시 단위(tonne/mm3)로
  오고 `density_unit` 이 함께 온다 — 필드 이름에 단위를 박았다가 알루미늄이
  `2.68e-09 kg/m3` 로 나갔다. 지금은 값과 단위를 함께 싣는다. **반대로 카드
  API(`POST /fitting/cards`)의 `density` 는 SI(kg/m³)다** — 재료 API 의 숫자를
  그대로 옮기면 서버가 범위 밖(0.5~50,000)이라고 거절한다(2026-09-11). 선언
  물성·물려받는 값도 이제 `si_unit` 을 함께 싣는다 — 값만 넘기던 자리였다.
- **감사에는 사람과 AI 가 함께 남는다.** 서버가 `X-Client: mcp` 를 붙이고,
  누가 한 일인지는 토큰이 말한다 — 감사 화면에 「홍길동 · AI(MCP) 경유」 로
  나온다. 헤더 값은 latin-1 이라 한글은 애초에 못 보낸다(`mcp|pylon|script`).
- **이 폴더는 백엔드 ruff 대상이 아니다.** `backend` 에서 `ruff format .` 을
  돌리며 여기까지 걸면 한 번도 포맷된 적 없는 `server.py` 가 통째로 다시 써진다
  — 실제로 그렇게 했다가 되돌렸다(2026-09-08). 여기는 손으로 맞춘다.
- **덱의 MID 는 파일 안에서만 유일하다.** 카드 UUID 에서 만든 수라, 낱개로 뽑은
  덱 여럿을 손으로 합치면 겹칠 수 있고 솔버는 조용히 덮는다. 그 수는
  `render_card_deck` 이 돌려주는 **덱 글자 안에** 있으니 읽어서 **사람에게 말해라**
  (따로 싣지 않는다 — 만드는 규칙을 두 벌로 두지 않으려고).
- **처음 MCP 로 불러 보고서야 넷이 죽어 있는 것을 알았다**(2026-09-10). 같은
  엔드포인트를 curl 로 부르면 전부 멀쩡했다 — MCP 로만 드러나는 층이 셋 있다:
  - **mcp 2.x 는 도구 결과를 반환 표기로 검증한다**(1.x 는 안 했다). `-> dict`
    라고 적고 목록 엔드포인트를 그대로 흘리면 pydantic 이 막고, 클라이언트에는
    `Error executing tool …` 만 간다. 셋이 그렇게 죽어 있었다 — `_listed(...)`
    로 감싸고, `tests/architecture/test_mcp_tools.py` 가 openapi 와 대조해 막는다.
  - **JSON 이 아닌 응답**: 덱은 `text/plain` 인데 `_get` 이 무조건 `.json()` 을
    불러 터졌다. `render_card_deck` 은 **한 번도 돌아간 적이 없었다.**
  - **오류의 자세한 내용을 버리고 있었다**: 「건너뛴 이유를 보세요」 라고 답하는데
    그 이유가 응답에 없었다. 백엔드는 `details` 에 실어 보내는데 message·code 만
    옮기고 있었다. 화면은 다른 자리에서 보여 주므로 API 로 부르는 쪽에만 났다.
- **클라이언트를 손으로 만들 때 타임아웃을 하나로 주지 마라.** `Timeout(60)` 을
  주면 SSE 수신 스트림까지 60초에 끊겨 **첫 호출부터** ReadTimeout 이 난다. SDK 의
  `create_mcp_http_client` 는 읽기만 300초로 따로 둔다.
