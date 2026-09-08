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

## 5. 지금 있는 것 (1단계)

    get_guide(topic?)                         규약 — 단위·값의 무게·층·흐름
    search_materials(query, family, ...)      재료 찾기 (번호·이름·별칭·분류)
    get_material(material_id)                 재료 하나 — 선언 물성·카드·문헌 연결
    matnexus://guide                          같은 안내를 리소스로

다음 단계(문헌 카탈로그·측정법·시험·덱)는 계획서의 2~3단계에 있다.

## 실측으로 잡은 것

- **mcp 2.x 에서 `FastMCP` → `MCPServer` 로 개명됐다.** 참고 구현 둘(MT·RA)은
  1.x 라 그대로 베끼면 안 된다.
- **의존성 충돌은 없었다**(2026-09-06): mcp 2.1.1 이 starlette 1.6.0 ·
  pydantic 2.13.5 로 우리 백엔드와 같은 줄이다. 그래도 분리는 유지한다.
- **밀도는 SI 가 아니다.** 재료 API 의 `density` 는 화면 표시 단위(tonne/mm3)로
  오고 `density_unit` 이 함께 온다 — 필드 이름에 단위를 박았다가 알루미늄이
  `2.68e-09 kg/m3` 로 나갔다. 지금은 값과 단위를 함께 싣는다.
