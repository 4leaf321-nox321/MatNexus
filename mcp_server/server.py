"""MatNexus MCP 서버 — **AI 가 물성 데이터를 직접 묻는다** (계획: docs/[계획] MCP 서버.md).

설계는 참고 구현 둘의 좋은 쪽을 각각 받았다:

    ReportArchive   뼈대·인증·운영 — PAT 를 그대로 나르고, 판정은 백엔드가 한다
    MaterialTwin    도구 설계·응답 — 값마다 근거(출처·등급·표지)가 함께 나간다

## 이 서버는 권한을 판정하지 않는다

받은 `Authorization` 헤더를 백엔드로 넘기기만 한다. **만능 토큰을 두지 않는다** —
서버가 자기 자격으로 부르면 그 순간 모든 사용자가 같은 권한을 갖는다. 부서
가시성·전역 재료·편집 권한은 지금 있는 코드가 판정한다(규칙이 두 벌이 되면
갈라지고, 갈라진 쪽이 MCP 면 그것은 권한 우회다).

## 얇은 프록시다 — DB 를 직접 안 읽는다

`httpx` 로 백엔드 REST 를 부른다. MaterialTwin 은 DB 를 직접 읽었지만 그쪽은
인증이 없었다. 필요한 계산이 생기면 **백엔드에 엔드포인트를 만든다.**

## 안내는 서버가 들고 매 호출 읽는다

`guide/GUIDE.md`. 클라이언트 쪽에 복사해 두면 **고쳐도 옛 사본을 쓰는 사람에게는
전달되지 않는다**(ReportArchive 실측). 파일만 고치면 재시작 없이 반영된다.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import httpx

# 같은 폴더 — 재시도 판단만 떼어 둔 순수 함수(시험이 부를 수 있게).
import retry_plan
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.transport_security import TransportSecuritySettings

#: 백엔드 API. 같은 기계에서 도는 것이 기본이다.
API_BASE = os.environ.get("MATNEXUS_API_BASE", "http://127.0.0.1:8010/api").rstrip("/")

#: 한 번에 돌려주는 목록의 상한. **도구가 스스로 막는다**(MaterialTwin 교훈:
#: 상한이 없으면 한 번의 호출이 수십만 자가 되어 대화가 끊긴다).
MAX_LIMIT = 50

GUIDE_PATH = Path(__file__).parent / "guide" / "GUIDE.md"

mcp = MCPServer(
    name="matnexus",
    instructions=(
        "MatNexus 재료 물성 플랫폼. 값에는 언제나 출처(origin·source·quality_tier)가"
        " 함께 오고, 숫자는 전부 SI 다. 먼저 get_guide() 를 읽어라 —"
        " 특히 tier 4(추정)와 synthetic(합성) 값을 실측처럼 옮기지 않는 규약이 있다."
    ),
)


# ── 백엔드 호출 ────────────────────────────────────────────────────────────────


def _headers(ctx: Context) -> dict[str, str]:
    """호출자의 자격을 그대로 나른다. **여기서 토큰을 만들지 않는다.**

    `X-Client` 는 감사 표식이지 보안 경계가 아니다 — 백엔드가 「이 변경은 MCP 로
    들어왔다」 를 기록할 수 있게 붙인다.
    """
    got = dict(ctx.headers or {})
    out = {"X-Client": "mcp"}
    for name in ("authorization", "Authorization"):
        if got.get(name):
            out["Authorization"] = got[name]
            break
    return out


async def _get(ctx: Context, path: str, params: dict[str, Any] | None = None) -> Any:
    """GET 하나. 오류는 **한국어 한 줄**로 바꿔 돌려준다.

    예외를 그대로 던지면 대화가 스택트레이스로 끊긴다 — 무엇이 잘못됐는지
    사람에게 옮길 수 있는 문장이어야 한다.
    """
    clean = {key: value for key, value in (params or {}).items() if value is not None}
    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
            got = await client.get(path, params=clean, headers=_headers(ctx))
    except httpx.RequestError as failed:
        return {"error": f"백엔드에 닿지 못했습니다({API_BASE}): {failed}"}
    if got.status_code == 401:
        return {
            "error": (
                "인증에 실패했습니다. MatNexus 화면의 「내 계정 → 토큰」 에서 발급한"
                " 개인 토큰(mnx_pat_…)을 Authorization 헤더로 등록했는지 확인하세요."
            )
        }
    if got.status_code == 403:
        return {"error": "권한이 없습니다 — 이 자료는 당신 계정으로 볼 수 없습니다."}
    if got.status_code >= 400:
        return _failed(got)
    return got.json()


def _failed(got: httpx.Response) -> dict[str, Any]:
    """오류 봉투를 **자세한 내용까지** 옮긴다.

    처음에는 message 와 code 만 옮겼는데, 그러면 「건너뛴 이유를 보세요」 같은
    안내가 가리키는 곳이 사라진다 — 백엔드는 `details` 에 실어 보내는데 여기서
    버리고 있었다(실측 2026-09-10, `build_deck`).
    """
    try:
        body = got.json()["error"]
    except Exception:
        return {"error": f"요청이 실패했습니다(HTTP {got.status_code})."}
    out: dict[str, Any] = {"error": f"{body.get('message')} ({body.get('code')})"}
    if body.get("details"):
        out["details"] = body["details"]
    return out


def _listed(payload: object, key: str) -> dict[str, object]:
    """목록을 dict 로 **감싼다.**

    **감싸지 않으면 그 도구는 통째로 죽는다.** mcp 2.x 는 도구가 돌려준 값을
    함수의 반환 표기(`-> dict[str, Any]`)로 검증하는데, 목록 엔드포인트는 배열을
    준다 — 그러면 pydantic 이 「dict 여야 한다」 로 막고 클라이언트에는
    `Error executing tool …` 만 간다. 무엇이 왜 틀렸는지가 사라진다.

    실측(2026-09-10): 진짜 MCP 클라이언트로 41개를 왕복해 보고서야 드러났다 —
    `get_parameter_sets` · `get_catalog_parameter_sets` · `list_recipes` 셋이
    그렇게 죽어 있었고, HTTP 로 같은 엔드포인트를 부르면 멀쩡했으므로 화면이나
    curl 로는 영영 안 보였다. `tests/architecture/test_mcp_tools.py` 가 이제
    같은 어긋남을 정적으로 막는다.

    오류 봉투(`{"error": …}`)는 이미 dict 이므로 그대로 흘려보낸다.
    """
    if isinstance(payload, dict):
        return payload
    rows = list(payload) if isinstance(payload, list) else []
    return {key: rows, "count": len(rows)}


async def _get_text(ctx: Context, path: str, params: dict[str, Any] | None = None) -> Any:
    """**글자로 오는 응답**을 읽는다 — 덱처럼 JSON 이 아닌 것.

    `_get` 은 무조건 `.json()` 을 부른다. 덱 내보내기는 `text/plain` 이라 거기서
    JSONDecodeError 로 터졌다(실측 2026-09-10). 형식에 따라 JSON 이 오기도 하므로
    (`format="json"`) 파싱이 되면 파싱해서 준다.
    """
    clean = {key: value for key, value in (params or {}).items() if value is not None}
    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=30.0) as client:
            got = await client.get(path, params=clean, headers=_headers(ctx))
    except httpx.RequestError as failed:
        return {"error": f"백엔드에 닿지 못했습니다({API_BASE}): {failed}"}
    if got.status_code >= 400:
        return _failed(got)
    return got.text


async def _send(
    ctx: Context, method: str, path: str, body: dict[str, Any] | None = None
) -> Any:
    """POST·PATCH 하나. **쓰기는 이 함수만 지난다** — 오류 모양을 한 곳에 둔다."""
    try:
        async with httpx.AsyncClient(base_url=API_BASE, timeout=60.0) as client:
            got = await client.request(
                method, path, json=body or {}, headers=_headers(ctx)
            )
    except httpx.RequestError as failed:
        return {"error": f"백엔드에 닿지 못했습니다({API_BASE}): {failed}"}
    if got.status_code == 401:
        return {"error": "인증에 실패했습니다 — 개인 토큰(mnx_pat_…)을 확인하세요."}
    if got.status_code == 403:
        return {"error": "권한이 없습니다 — 이 자료는 당신 계정으로 고칠 수 없습니다."}
    if got.status_code >= 400:
        return _failed(got)
    return got.json() if got.content else {"ok": True}


# ── 값에 근거를 붙인다 (D8) ────────────────────────────────────────────────────


def _declared_value(row: dict[str, Any]) -> dict[str, Any]:
    """선언 물성 한 줄 → **근거가 붙은 값.**

    `origin` 과 `caveat` 를 여기서 만든다 — 백엔드 응답에는 `source` 문자열만
    있고, 그 문자열이 무슨 무게인지는 이 계층이 안다.
    """
    points = row.get("points") or []
    source = str(row.get("source") or "")
    caveats: list[str] = []
    if source == "estimate":
        caveats.append("추정값 — 잰 값이 아니다")
    if source == "millsheet":
        caveats.append("밀시트 — 그 로트의 값이다")
    return {
        "item": row.get("item"),
        # **SI 값만 낸다.** `value` 는 사람이 적은 단위의 숫자라, 함께 주면
        # 어느 쪽이 정본인지 헷갈린다.
        "values_si": [
            {"temperature_k": one.get("temperature_k"), "value": one.get("value_si")}
            for one in points
        ],
        "origin": f"declared:{source}" if source else "declared",
        "source_document": row.get("reference"),
        "scale": row.get("scale"),
        "note": row.get("note"),
        **({"caveat": " · ".join(caveats)} if caveats else {}),
    }


def _card_summary(card: dict[str, Any]) -> dict[str, Any]:
    """카드 한 장 요약 — **초안인지, 지어낸 표가 실렸는지**를 말한다."""
    source = card.get("source") or {}
    caveats: list[str] = []
    if card.get("status") == "draft":
        caveats.append("초안 카드 — 아직 확정되지 않았다")
    if card.get("status") == "deprecated":
        caveats.append("사용 중지된 카드")
    if source.get("declared_only"):
        caveats.append("시험값이 하나도 없다 — 적어 둔 값으로만 만들었다")
    synthetic = source.get("synthetic_plastic")
    if synthetic:
        caveats.append(f"합성 소성 표 — 실측이 아니다({synthetic.get('model')})")
    return {
        "id": card.get("id"),
        "label": card.get("label"),
        "status": card.get("status"),
        "test_type": card.get("test_type_key"),
        "orientation": card.get("orientation"),
        "blocks": sorted((card.get("blocks") or {}).keys()),
        "available_formats": card.get("available_formats") or [],
        "sample_count": source.get("sample_count"),
        **({"caveat": " · ".join(caveats)} if caveats else {}),
    }


# ── 도구 ──────────────────────────────────────────────────────────────────────


@mcp.tool()
def get_guide(topic: str | None = None) -> str:
    """MatNexus 사용 규약 — **먼저 읽어라.**

    단위(전부 SI) · 값의 무게(origin·quality_tier·caveat) · 선언 물성의 층 ·
    전형적인 흐름이 적혀 있다. `topic` 으로 한 절만 받을 수 있다:
    `overview` · `units` · `properties` · `trust` · `layers` · `ontology` ·
    `processing` · `definitions` · `cards` · `workflow` · `limits`.
    """
    try:
        text = GUIDE_PATH.read_text(encoding="utf-8")
    except OSError as failed:
        return f"안내 문서를 읽지 못했습니다: {failed}"
    if not topic:
        return text
    # `<!--@ 이름 -->` 마커로 절을 자른다 — 안내가 길어져도 필요한 만큼만 낸다.
    marker = f"<!--@ {topic} -->"
    if marker not in text:
        return f"모르는 주제입니다: {topic}. 인자 없이 부르면 전체가 나옵니다."
    body = text.split(marker, 1)[1]
    return body.split("<!--@", 1)[0].strip()


@mcp.tool()
async def search_materials(
    ctx: Context,
    query: str | None = None,
    family: str | None = None,
    category: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """사내 재료를 찾는다 — 이름·별칭·분류·**재료 번호**로.

    `query` 는 낱말마다 나눠 AND 로 찾는다(`SECC 1.0` 처럼 순서와 무관). 재료
    번호는 `M-000123` 도 `M-123` 도 닿는다.

    돌려주는 것은 목록이라 값은 안 실린다 — 물성은 `get_material(id)` 로 본다.
    """
    got = await _get(
        ctx,
        "/materials",
        {
            "q": query,
            "family": family,
            "category": category,
            "limit": max(1, min(limit, MAX_LIMIT)),
        },
    )
    if "error" in got:
        return got
    return {
        "total": got.get("total", 0),
        "shown": len(got.get("items", [])),
        "materials": [
            {
                "id": one["id"],
                # **번호를 먼저 낸다.** 이름은 기준정보 개명을 따라 바뀌지만
                # 번호는 안 바뀐다 — 문서에 적을 것은 이쪽이다.
                "code": one.get("code"),
                "name": one.get("record_name"),
                "alias": one.get("alias"),
                "family": one.get("family"),
                "category": one.get("category"),
                "grade": one.get("grade"),
                "workspace": one.get("owner_workspace_name"),
                "is_global": one.get("is_global"),
                "sample_count": one.get("sample_count"),
            }
            for one in got.get("items", [])
        ],
    }


@mcp.tool()
async def get_material(ctx: Context, material_id: str) -> dict[str, Any]:
    """재료 하나 — 기본 칸·선언 물성·물성 카드·문헌 연결.

    **모든 값에 `origin` 이 붙는다**(measured · declared:… · synthetic · catalog).
    `caveat` 가 있으면 그대로 사람에게 전한다 — 초안 카드나 합성 표를 실측처럼
    옮기면 그 값으로 해석이 돌아간다.

    **선언 물성(`declared_properties`)의 값은 정본 SI** 다(응력 Pa · 온도 K).
    재료 기본 칸(`basics`)은 값과 **단위가 함께** 오니 그 단위로 읽어라 — 밀도는
    화면 표시 단위(tonne/mm3 등)일 수 있다.
    """
    material = await _get(ctx, f"/materials/{material_id}")
    if "error" in material:
        return material

    cards = await _get(ctx, "/fitting/cards", {"material_id": material_id, "limit": 20})
    link = await _get(ctx, f"/catalog/links/{material_id}")

    basics: dict[str, Any] = {}
    if material.get("density") is not None:
        # **단위를 이름에 박지 않는다.** 재료 API 의 밀도는 SI 가 아니라 화면
        # 표시 단위(tonne/mm3 등)로 오고 `density_unit` 이 함께 온다 — 실측
        # (2026-09-06)에서 2680 kg/m3 인 알루미늄이 `density_kg_m3: 2.68e-09` 로
        # 나갔다. 환산은 여기서 안 한다(규칙이 두 벌이 되면 갈라진다) — 값과
        # 단위를 함께 실어 읽는 쪽이 단위를 보고 말하게 한다.
        basics["density"] = {
            "value": material["density"],
            "unit": material.get("density_unit"),
            "origin": "declared:material",
            "caveat": "재료의 공칭값 — 시료 실측이 있으면 카드는 그쪽을 먼저 쓴다",
        }
    if material.get("poisson_ratio") is not None:
        basics["poisson_ratio"] = {
            "value": material["poisson_ratio"],
            "unit": "1",
            "origin": "declared:material",
        }

    out: dict[str, Any] = {
        "id": material["id"],
        "code": material.get("code"),
        "name": material.get("record_name"),
        "alias": material.get("alias"),
        "classification": {
            "family": material.get("family"),
            "category": material.get("category"),
            "grade": material.get("grade"),
            "details": material.get("details"),
        },
        "workspace": material.get("owner_workspace_name"),
        "is_global": material.get("is_global"),
        "basics": basics,
        "declared_properties": [
            _declared_value(row) for row in material.get("declared_properties") or []
        ],
        "sample_count": material.get("sample_count"),
        "note": material.get("note"),
    }
    if isinstance(cards, dict) and "error" not in cards:
        out["cards"] = [_card_summary(one) for one in cards.get("items", [])]
    if isinstance(link, dict) and "error" not in link and link.get("catalog_material_id"):
        out["catalog_link"] = {
            "catalog_material_id": link["catalog_material_id"],
            "name": link.get("name"),
            "value_count": link.get("value_count"),
            "hint": "문헌 값은 catalog 도구로 본다 — quality_tier 를 함께 읽어라",
        }
    return out


@mcp.tool()
async def list_unit_systems(ctx: Context) -> dict[str, Any]:
    """덱을 낼 수 있는 **단위계 목록** — 덱을 뽑기 전에 먼저 고른다.

    솔버 덱은 단위를 선언하지 않는다(LS-DYNA 가 그렇다). 그래서 **한 덱 안의
    모든 재료가 같은 계여야 하고**, 계가 섞이면 조용히 1000배 틀린 답이 나온다 —
    이 목록의 `key` 를 덱 도구에 그대로 넘긴다.

    `declaration` 은 덱 머리에 적히는 줄이다(`tonne, mm, s, MPa`). 사용자가 만든
    계도 함께 나온다(`builtin=false`).
    """
    got = await _get(ctx, "/fitting/unit-systems")
    if isinstance(got, dict) and "error" in got:
        return got
    return {
        "systems": [
            {
                "key": one.get("key"),
                "label": one.get("label"),
                "declaration": one.get("declaration"),
                "is_default": one.get("is_default"),
                "builtin": one.get("builtin"),
            }
            for one in got
        ],
        "hint": (
            "덱 도구의 units 인자에 key 를 넘긴다. 안 고르면 SI 로 나가는데,"
            " 받는 쪽 해석 모델이 mm·tonne 계면 그대로 쓰면 안 된다."
        ),
    }


# ── 문헌 카탈로그 (2단계) ─────────────────────────────────────────────────────


def _catalog_value(row: dict[str, Any]) -> dict[str, Any]:
    """문헌 값 하나 → **등급과 출처가 붙은 값.**

    tier 4 는 계산·추정·가정이다 — 이 표지가 빠지면 AI 가 그 숫자를 실측처럼
    옮긴다. 대표가 아닌 값도 숨기지 않는다(왜 밀렸는지 함께 낸다).
    """
    tier = row.get("quality_tier")
    source = row.get("source") or {}
    caveats: list[str] = []
    if tier == 4:
        caveats.append("tier 4 — 계산·추정·가정이다. 실측이 아니다")
    if (row.get("conditions") or {}).get("assumption") is True:
        caveats.append("가정값으로 표시돼 있다")
    if not row.get("representative"):
        caveats.append(f"대표값이 아니다(밀린 자리: {row.get('separated_by')})")
    return {
        "property": row.get("property_name"),
        "property_key": row.get("property_key"),
        "domain": row.get("domain"),
        "value": (
            row.get("value_num") if row.get("value_num") is not None else row.get("value_text")
        ),
        "unit": row.get("unit"),
        "uncertainty": row.get("uncertainty"),
        "conditions": row.get("conditions"),
        "method": row.get("method"),
        "quality_tier": tier,
        "origin": "catalog",
        "source": (
            {
                "title": source.get("title"),
                "year": source.get("year"),
                "doi": source.get("doi"),
                "kind": source.get("kind"),
                "detail": row.get("source_detail"),
            }
            if source
            else None
        ),
        "representative": row.get("representative"),
        **({"caveat": " · ".join(caveats)} if caveats else {}),
    }


@mcp.tool()
async def search_catalog(
    ctx: Context, query: str, category: str | None = None, limit: int = 10
) -> dict[str, Any]:
    """**문헌 물성 카탈로그**에서 재료를 찾는다(42,209건 · 출처와 등급이 붙어 있다).

    사내 재료(`search_materials`)와 **다른 세계**다 — 여기는 실물 없이 문헌·
    데이터시트에서 채굴한 값이고, 사내 재료와는 연결·채택으로 만난다.

    값은 안 실린다(재료마다 수십 건이다) — `get_catalog_material(id)` 로 본다.
    """
    got = await _get(
        ctx,
        "/catalog/materials",
        {"q": query, "category": category, "limit": max(1, min(limit, MAX_LIMIT))},
    )
    if "error" in got:
        return got
    return {
        "total": got.get("total", 0),
        "materials": [
            {
                "id": one["id"],
                "name": one.get("name"),
                "category": one.get("category"),
                "subsystem": one.get("subsystem"),
                "manufacturer": one.get("manufacturer"),
                "grade": one.get("grade"),
                "value_count": one.get("value_count"),
            }
            for one in got.get("items", [])
        ],
        "hint": "값이 많은 재료가 먼저 온다 — 쓸 것이 많다는 뜻이다.",
    }


@mcp.tool()
async def get_catalog_material(
    ctx: Context,
    catalog_material_id: str,
    domain: str | None = None,
    property_keys: list[str] | None = None,
    limit: int = 60,
) -> dict[str, Any]:
    """문헌 재료 하나의 **물성** — 값·조건·등급·출처.

    같은 물성에 값이 여럿이면 **대표값이 먼저** 오고 밀린 후보도 이유와 함께
    온다(`representative`·`separated_by`).

    ## 좁혀서 물어라 — 안 그러면 답이 안 읽힌다

    값이 786개인 재료가 있다(솔더 합금: Anand 상수만 224개). 전부 받으면 응답이
    수 MB 가 되고, 그러면 **당신의 문맥이 그것으로 다 찬다** — 실측(2026-09-10):
    AI 가 이 응답을 다 못 읽어서 제 대화 기록을 뒤져 물성 키를 찾아냈다.

        domain          `mechanical`·`thermal`·`physical`·`electrical`·`optical`
        property_keys   아는 키만 콕 집는다 (`resolve_property` 로 푼 것)
        limit           기본 60. 잘리면 `omitted` 로 몇 개가 남았는지 말해 준다

    **파라미터 벌(Anand·Prony 같은 것)은 여기서 찾지 마라.** 낱개로 흩어져 보이는
    데다 개수가 많다 — `get_catalog_parameter_sets` 가 벌로 묶어 준다.

    **tier 4 는 추정·가정이다.** `caveat` 가 붙은 값을 실측처럼 옮기지 않는다.
    """
    got = await _get(ctx, f"/catalog/materials/{catalog_material_id}")
    if "error" in got:
        return got
    wanted = {one.lower() for one in property_keys or []}
    rows = [
        row
        for row in got.get("values", [])
        if (not domain or row.get("domain") == domain)
        and (not wanted or str(row.get("property_key", "")).lower() in wanted)
    ]
    total = len(rows)
    # **대표값을 먼저 남긴다.** 잘라야 한다면 밀린 후보부터 버리는 것이 맞다 —
    # 받아 갈 수 있는 값은 대표값이다.
    rows.sort(key=lambda one: (not one.get("representative"), one.get("quality_tier") or 9))
    cut = max(1, limit)
    values = [_catalog_value(row) for row in rows[:cut]]
    tiers: dict[str, int] = {}
    for one in values:
        key = f"tier{one['quality_tier']}"
        tiers[key] = tiers.get(key, 0) + 1
    return {
        "id": got["id"],
        "name": got.get("name"),
        "category": got.get("category"),
        "subsystem": got.get("subsystem"),
        "manufacturer": got.get("manufacturer"),
        "material_class": got.get("material_class"),
        "grade": got.get("grade"),
        "description": got.get("description"),
        "total_values": total,
        "shown_values": len(values),
        "omitted": max(0, total - len(values)),
        "tier_counts": tiers,
        "values": values,
        **(
            {
                "hint": (
                    f"{total - len(values)}개를 안 보였습니다. `domain` 이나 "
                    "`property_keys` 로 좁히세요 — 파라미터 벌은 "
                    "`get_catalog_parameter_sets` 가 묶어 줍니다."
                )
            }
            if total > len(values)
            else {}
        ),
    }


# ── 측정법 (2단계) ────────────────────────────────────────────────────────────


@mcp.tool()
async def how_to_measure(ctx: Context, property_key: str) -> dict[str, Any]:
    """**이 물성은 무엇으로 어떻게 재는가** — 기법·시험 규격·장비.

    `property_key` 는 카탈로그 물성 키다(`mechanical.youngs_modulus` 처럼 —
    `get_catalog_material` 응답의 `property_key` 를 그대로 넘긴다).

    **장비 카탈로그에 있는 것과 우리가 보유한 것은 다르다** — `owned` 를 보고
    말한다. 「잴 수 있다」 와 「그런 장비가 세상에 있다」 는 다른 말이다.
    """
    got = await _get(ctx, f"/metrology/by-property/{property_key}")
    if "error" in got:
        # **도메인을 안 붙이면 못 찾는다.** `yield_strength` 가 아니라
        # `mechanical.yield_strength` 다 — 다음 수를 알려 주지 않으면 AI 는
        # 「그 물성은 못 잽니다」 로 결론지어 사람에게 옮긴다(실측 2026-09-10).
        if "." not in property_key:
            got = dict(got)
            got["hint"] = (
                f"'{property_key}' 에 도메인이 안 붙었습니다. `resolve_property"
                f"(\"{property_key}\")` 로 온전한 키를 먼저 푸세요 —"
                " `mechanical.yield_strength` 같은 모양이어야 합니다."
            )
        return got
    techniques = []
    for group in got.get("techniques", []):
        rows = []
        for one in group.get("capabilities", []):
            instrument = one.get("instrument") or {}
            rows.append(
                {
                    "instrument": f"{instrument.get('vendor')} {instrument.get('model')}",
                    "owned": instrument.get("owned"),
                    "owner": instrument.get("owner_name"),
                    "standard": one.get("standard"),
                    "range": [
                        one.get("range_min"),
                        one.get("range_max"),
                        one.get("range_unit"),
                    ],
                    "specimen_temperature_k": [
                        one.get("temperature_min_k"),
                        one.get("temperature_max_k"),
                    ],
                    "resolution": one.get("resolution"),
                    "accuracy": one.get("accuracy"),
                    **(
                        {"caveat": "물성-장비 매핑 확신도가 낮다 — 확인이 필요하다"}
                        if one.get("mapping_confidence") not in (None, "high")
                        else {}
                    ),
                }
            )
        techniques.append(
            {"technique": group.get("technique") or "기법 미정", "instruments": rows}
        )
    owned = sum(1 for group in techniques for one in group["instruments"] if one.get("owned"))
    return {
        "property": got.get("name"),
        "property_key": got.get("property_key"),
        "si_unit": got.get("si_unit"),
        "test_standard": got.get("test_standard"),
        "owned_instrument_count": owned,
        "techniques": techniques,
        **(
            {"caveat": "보유 장비가 없다 — 이 물성은 외주하거나 문헌값을 써야 한다"}
            if owned == 0
            else {}
        ),
    }


# ── 시험과 카드 (2단계) ───────────────────────────────────────────────────────


@mcp.tool()
async def list_test_runs(
    ctx: Context,
    material_id: str | None = None,
    query: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """시험 목록 — 재료로 좁히거나 이름으로 찾는다.

    `adopted` 가 참인 시험만 「그 시험의 물성이 정해진」 것이다(ADR 0007) —
    채택 안 된 결과를 물성으로 옮기지 않는다.
    """
    got = await _get(
        ctx,
        "/test-runs",
        {"material_id": material_id, "q": query, "limit": max(1, min(limit, MAX_LIMIT))},
    )
    if "error" in got:
        return got
    return {
        "total": got.get("total", 0),
        "runs": [
            {
                "id": one["id"],
                "name": one.get("record_name"),
                "test_type": one.get("test_type_key"),
                "status": one.get("status"),
                "adopted": bool(one.get("adopted_result_id")),
                "result_count": one.get("result_count"),
                "master_curve_count": one.get("master_curve_count"),
                **(
                    {"caveat": "읽기에 실패한 시험이다 — 값이 없다"}
                    if one.get("status") == "failed"
                    else {}
                ),
            }
            for one in got.get("items", [])
        ],
    }


@mcp.tool()
async def get_test_run(ctx: Context, test_run_id: str) -> dict[str, Any]:
    """시험 하나 — 조건과 **채택된 처리 결과의 물성값**.

    처리 결과가 여럿이면 **채택된 것만** 값으로 옮긴다 — 나머지는 「시험해 본
    것」이지 「결론」이 아니다. 곡선 점은 안 낸다(수천 점이다).
    """
    run = await _get(ctx, f"/test-runs/{test_run_id}")
    if "error" in run:
        return run
    results = await _get(ctx, "/processing/results", {"test_run_id": test_run_id})
    scalars: list[dict[str, Any]] = []
    adopted_label = None
    if isinstance(results, list):
        for one in results:
            if not one.get("is_adopted"):
                continue
            adopted_label = one.get("recipe_label") or one.get("recipe_key")
            for value in one.get("scalars", []):
                scalars.append(
                    {
                        "key": value.get("key"),
                        "label": value.get("label"),
                        "value": value.get("value"),
                        "unit": value.get("si_unit"),
                        "origin": "measured",
                    }
                )
    return {
        "id": run["id"],
        "name": run.get("record_name"),
        "test_type": run.get("test_type_key"),
        "status": run.get("status"),
        "conditions": run.get("conditions"),
        "material_id": run.get("material_id"),
        "adopted_recipe": adopted_label,
        "measured_values_si": scalars,
        **(
            {"caveat": "채택된 처리 결과가 없다 — 이 시험의 물성은 아직 정해지지 않았다"}
            if not scalars
            else {}
        ),
    }


@mcp.tool()
async def get_card(ctx: Context, card_id: str) -> dict[str, Any]:
    """물성 카드 하나 — **덱에 실릴 값 그대로.**

    블록(`elastic`·`table`·`hardening`·`thermal` …)의 값이 SI 로 들어 있다.
    소성 표는 점이 많아 **개수와 앞뒤 몇 점만** 낸다.

    `caveat` 를 반드시 함께 전한다 — 초안 카드나 합성 소성 표를 확정된 실측처럼
    옮기면 그 값으로 해석이 돌아간다.
    """
    card = await _get(ctx, f"/fitting/cards/{card_id}")
    if "error" in card:
        return card
    blocks: dict[str, Any] = {}
    for name, payload in (card.get("blocks") or {}).items():
        if not isinstance(payload, dict):
            continue
        one: dict[str, Any] = {}
        if payload.get("values"):
            one["values_si"] = payload["values"]
        rows = payload.get("rows") or []
        if rows:
            # **표는 통째로 안 낸다.** 수천 점이면 대화가 그것으로 찬다.
            one["rows"] = {
                "count": len(rows),
                "first": rows[0],
                "last": rows[-1],
                "note": "표 전체가 필요하면 덱으로 받아라",
            }
        blocks[name] = one
    out = _card_summary(card)
    out["material"] = card.get("material_name")
    out["blocks_detail"] = blocks
    out["source"] = {
        "test_run_ids": (card.get("source") or {}).get("test_run_ids"),
        "notes": (card.get("source") or {}).get("notes"),
    }
    return out

# ── 덱 (3단계) ────────────────────────────────────────────────────────────────


@mcp.tool()
async def match_bom(ctx: Context, text: str) -> dict[str, Any]:
    """부품표(BOM)를 붙여넣어 **문헌 재료 후보**를 찾는다.

    한 줄이 `101, SUS304` 또는 `SUS304` 다(앞 숫자는 솔버의 재료 번호 MID).
    돌려주는 것은 **후보**지 확정이 아니다 — 어느 것을 쓸지는 사람이 정하고,
    그 결정을 `build_deck` 에 넘긴다.

    사내 재료(실측 카드)를 쓰려면 `search_materials` 로 찾아 그 카드 id 를
    `build_deck` 에 넘긴다 — **실측이 있으면 실측이 먼저다.**
    """
    got = await _send(ctx, "POST", "/catalog/deck/match", {"text": text})
    if "error" in got:
        return got
    return {
        "rows": [
            {
                "query": one.get("query"),
                "mid": one.get("mid"),
                "candidates": [
                    {
                        "catalog_material_id": c.get("id"),
                        "name": c.get("name"),
                        "value_count": c.get("value_count"),
                        "score": c.get("score"),
                    }
                    for c in one.get("candidates", [])
                ],
            }
            for one in got
        ],
        "hint": (
            "score 3=정확 일치 · 2=앞부분 · 1=포함. 후보가 없으면 이름이 다른 것이니"
            " 사람에게 확인한다 — 비슷한 이름을 임의로 고르지 않는다."
        ),
    }


#: 한 번에 나를 덱 줄 수. **넘으면 자르고 몇 줄이 남았는지 말한다** — 조용히
#: 잘라 주면 받는 사람이 온전한 파일인 줄 알고 저장한다.
MAX_DECK_LINES = 500


def _deck_body(text: str, include_text: bool) -> dict[str, Any]:
    """덱 본문을 실을지 정한다.

    처음에는 본문을 아예 안 냈다 — 「파일이 필요하면 화면에서 받아라」. 그런데
    그러면 **AI 로 끝까지 가는 길이 여기서 끊긴다**(실측 2026-09-10): 단위계를
    맞춘 덱을 서버가 만들어 놓고 본문을 안 주니, AI 가 SI 덱을 받아 손으로
    환산해 채워 넣었다. 고정폭 필드에 손대는 일이라 한 칸만 어긋나도 솔버가
    다른 값을 조용히 읽는다.

    그래서 **달라고 하면 준다.** 다만 상한을 둔다 — 대화가 덱으로 차면 그다음
    판단을 할 자리가 없어진다.
    """
    if not include_text:
        return {
            "note": (
                "본문은 안 실었다. 필요하면 `include_text=True` 로 다시 부르거나"
                " 화면(카드 → BOM 혼합 덱)에서 받는다."
            )
        }
    lines = text.splitlines()
    if len(lines) <= MAX_DECK_LINES:
        return {"deck": text}
    return {
        "deck": "\n".join(lines[:MAX_DECK_LINES]),
        "truncated": len(lines) - MAX_DECK_LINES,
        "note": (
            f"**잘렸다.** {len(lines)}줄 중 {MAX_DECK_LINES}줄만 실었다 — 이대로"
            " 저장하면 안 되는 파일이다. 온전한 파일은 화면(카드 → BOM 혼합 덱)"
            "에서 받는다."
        ),
    }


@mcp.tool()
async def build_deck(
    ctx: Context,
    rows: list[dict[str, Any]],
    units: str | None = None,
    include_text: bool = False,
    synthesize_missing_curves: bool = False,
) -> dict[str, Any]:
    """확정된 부품 목록 → **해석용 덱 한 파일**(LS-DYNA).

    `rows` 는 부품마다 하나씩, 이렇게 준다:

        {"mid": 1, "name": "도어 이너", "card_id": "<사내 카드 id>"}
        {"mid": 2, "name": "힌지", "catalog_material_id": "<문헌 재료 id>"}

    사내 카드가 있으면 **곡선 덱**(*MAT_024)으로, 문헌만 있으면 스칼라 덱으로
    나가고 한 파일로 합쳐진다. 값마다 출처 각주가 파일 안에 들어간다.

    `units` 는 `list_unit_systems()` 의 key 다. **안 주면 SI 로 나간다** —
    받는 쪽 모델이 mm·tonne 계면 그대로 쓰면 안 되니 어느 계로 뽑았는지 사람에게
    반드시 말한다.

    `synthesize_missing_curves=True` 면 문헌 스칼라로 **곡선을 지어** 소성 덱까지
    낸다 — 지어낸 곡선은 덱 각주에 「합성 — 실측이 아니다」 로 남고, 사람에게도
    그렇게 전해야 한다. 기본은 꺼져 있다.

    ## 파일을 건네려면 `include_text=True`

    기본은 머리(출처 각주)와 개수만 온다 — 수백 줄이면 대화가 그것으로 찬다.
    사람이 파일로 저장할 것이면 켜서 본문을 받아라. 500줄이 넘으면 잘리고 몇 줄이
    남았는지 함께 온다 — **잘린 것을 저장하면 안 되는 파일이다.**

    **본문을 손으로 고치지 마라.** 단위가 다르면 `units` 로 다시 뽑아라. 고정폭
    필드에 손대는 일이고, 한 칸만 어긋나도 솔버는 다른 값을 조용히 읽는다.
    """
    payload = {
        "rows": [
            {
                "mid": one.get("mid"),
                "name": one.get("name") or "",
                "card_id": one.get("card_id"),
                "catalog_material_id": one.get("catalog_material_id"),
                "synthesize": bool(synthesize_missing_curves and not one.get("card_id")),
            }
            for one in rows
        ],
        "units": units,
    }
    got = await _send(ctx, "POST", "/fitting/decks/bom", payload)
    if "error" in got:
        return got
    text = got.get("text", "")
    return {
        "filename": got.get("filename"),
        "line_count": len(text.splitlines()),
        "card_count": got.get("card_count"),
        "literature_count": got.get("literature_count"),
        "synthetic_count": got.get("synthetic_count", 0),
        "skipped": got.get("skipped", []),
        # **기본은 머리(출처 각주)만이다.** 수백 줄이면 대화가 그것으로 찬다.
        "header": "\n".join(
            line for line in text.splitlines()[:40] if line.startswith(("$", "*"))
        ),
        **_deck_body(text, include_text),
        **(
            {"caveat": f"합성 곡선 {got.get('synthetic_count')}건이 실렸다 — 실측이 아니다"}
            if got.get("synthetic_count")
            else {}
        ),
    }


# ── 제한적 쓰기 (3단계) ───────────────────────────────────────────────────────
#
# **확정·삭제·게시는 도구를 안 낸다.** 되돌리기 비싸고, 사람이 화면에서 하는
# 편이 낫다. 여기 있는 둘은 초안까지만 만든다.


@mcp.tool()
async def adopt_catalog_values(
    ctx: Context,
    material_id: str,
    catalog_material_id: str,
    property_keys: list[str],
    dry_run: bool = True,
) -> dict[str, Any]:
    """문헌 값을 **사내 재료의 선언 물성으로 담는다**(스냅샷).

    담은 값은 복사본이라 카탈로그를 다시 이관해도 조용히 안 바뀌고, 출처·등급이
    참고문헌 문자열로 따라간다.

    **기본이 미리보기(dry_run=True)다** — 무엇이 담길지 먼저 보이고, 사람이
    확인한 뒤에 `dry_run=False` 로 다시 부른다. 이미 있는 항목은 **덮어쓴다**.

    `property_keys` 는 `get_catalog_material` 의 `property_key` 들이다.
    tier 4(추정) 값도 담을 수 있지만, 담기 전에 그 사실을 사람에게 말한다.
    """
    detail = await _get(ctx, f"/catalog/materials/{catalog_material_id}")
    if "error" in detail:
        return detail
    material = await _get(ctx, f"/materials/{material_id}")
    if "error" in material:
        return material

    wanted = set(property_keys)
    picked = [
        row
        for row in detail.get("values", [])
        if row.get("property_key") in wanted
        and row.get("representative")
        and row.get("value_num") is not None
    ]
    if not picked:
        return {
            "error": (
                "담을 값이 없습니다 — property_key 가 맞는지, 그 물성에 수치 대표값이"
                " 있는지 get_catalog_material 로 확인하세요."
            )
        }

    # 매핑은 백엔드 mapping.PROPERTY_ITEM_MAP 이 정본이다. 여기서는 그 표를
    # 다시 쓰지 않고 **채택 가능한 것만** 추려 화면과 같은 PATCH 를 만든다.
    items = {
        "mechanical.youngs_modulus": ("declared", "탄성계수"),
        "mechanical.shear_modulus": ("declared", "전단탄성계수"),
        "mechanical.yield_strength": ("declared", "항복강도"),
        "mechanical.tensile_strength": ("declared", "인장강도"),
        "mechanical.elongation_at_break": ("declared", "연신율"),
        "thermal.specific_heat": ("declared", "비열"),
        "thermal.conductivity": ("declared", "열전도율"),
        "thermal.expansion_linear": ("declared", "선팽창계수(CTE)"),
        "physical.density": ("column", "density"),
        "mechanical.poisson_ratio": ("column", "poisson_ratio"),
    }
    kinds = {"journal": "literature", "book": "literature", "database": "literature",
             "web": "literature", "other": "literature", "standard": "standard",
             "datasheet": "datasheet"}

    planned: list[dict[str, Any]] = []
    declared: list[dict[str, Any]] = []
    patch: dict[str, Any] = {}
    for row in picked:
        target = items.get(row["property_key"])
        if target is None:
            planned.append({"property_key": row["property_key"], "skipped": "담을 자리가 없는 물성"})
            continue
        place, name = target
        source = row.get("source") or {}
        origin = "estimate" if row.get("quality_tier") == 4 else kinds.get(source.get("kind"), "literature")
        reference = " · ".join(
            part
            for part in (source.get("title"), str(source.get("year") or "") or None,
                         row.get("source_detail"))
            if part
        ) or "문헌 카탈로그"
        reference = f"{reference} [tier {row.get('quality_tier')}]"
        if place == "column":
            if name == "density":
                patch["density"], patch["density_unit"] = row["value_num"], "kg/m3"
            elif 0 <= row["value_num"] < 0.5:
                patch["poisson_ratio"] = row["value_num"]
            else:
                planned.append({"property": name, "skipped": "서버 제약 밖의 값(0 ≤ ν < 0.5)"})
                continue
        else:
            declared.append(
                {
                    "item": name,
                    "points": [{"value": row["value_num"]}],
                    "source": origin,
                    "reference": reference,
                    "note": "문헌 물성 카탈로그에서 채택 (스냅샷)",
                }
            )
        planned.append(
            {
                "property": name,
                "value_si": row["value_num"],
                "unit": row.get("unit"),
                "quality_tier": row.get("quality_tier"),
                "source": reference,
                **({"caveat": "tier 4 — 추정·가정값이다"} if row.get("quality_tier") == 4 else {}),
            }
        )

    if dry_run:
        return {
            "dry_run": True,
            "material": material.get("record_name"),
            "will_adopt": planned,
            "note": "이대로 담으려면 dry_run=False 로 다시 부르세요. 이미 있는 항목은 덮어씁니다.",
        }

    if declared:
        # **선언 물성은 통째 교체다** — 기존 줄을 되보내고 담는 것만 더한다.
        keep = {one["item"] for one in declared}
        merged = [
            {
                "item": row["item"],
                "points": [
                    {"temperature_k": p.get("temperature_k"), "value": p.get("value")}
                    for p in row.get("points", [])
                ],
                "input_unit": row.get("input_unit"),
                "scale": row.get("scale"),
                "source": row.get("source"),
                "reference": row.get("reference"),
                "note": row.get("note"),
            }
            for row in material.get("declared_properties", [])
            if row.get("item") not in keep
        ]
        patch["declared_properties"] = merged + declared

    done = await _send(ctx, "PATCH", f"/materials/{material_id}", patch)
    if "error" in done:
        return done
    return {
        "ok": True,
        "material": done.get("record_name"),
        "adopted": planned,
        "note": "담은 값은 스냅샷이다 — 카탈로그를 다시 이관해도 안 바뀐다.",
    }


@mcp.tool()
async def preview_card_fit(
    ctx: Context,
    material_id: str,
    test_type: str,
    orientation: str,
    test_run_ids: list[str] | None = None,
    families: list[str] | None = None,
    extrapolate_to: float | None = None,
) -> dict[str, Any]:
    """시험 곡선에 **여러 경화식을 맞춰 견준다** — 저장하지 않는다.

    카드를 만들기 전에 여기부터 온다. 대표 곡선을 뽑고 등록된 식들을 각각 맞춰
    상대 RMSE 와 적합 구간을 돌려준다.

    ## **RMSE 로 고르지 마라**

    이 도구는 순서를 매겨 주지만 **어느 것이 맞는지 고르지 않는다.** 적합 구간에서
    거의 같은 두 식이 그 밖에서 크게 갈리기 때문이다 — Swift 는 과대, Voce 는 과소
    예측하는 경향이 알려져 있고, 어디까지 쓸 것인지는 해석하는 사람이 안다.
    후보를 사람에게 보이고 **골라 달라고 해라.**

    `extrapolate_to` 로 그 구간 밖까지 늘려 그려 볼 수 있다 — 두 식이 얼마나
    갈리는지 숫자로 보여 줄 수 있다.

    `test_run_ids` 를 주면 **그 시험들만** 쓴다(이상치 하나를 빼고 다시 보는 것이
    실무의 정상 작업이다). 비우면 채택된 것 전부.
    """
    answer = await _send(
        ctx,
        "POST",
        "/fitting/preview",
        {
            "material_id": material_id,
            "test_type_key": test_type,
            "orientation": orientation,
            "test_run_ids": test_run_ids,
            "families": families or [],
            "extrapolate_to": extrapolate_to,
        },
    )
    if not isinstance(answer, dict):
        return {"error": "적합 응답을 읽지 못했습니다."}
    if "error" in answer:
        return answer

    # **곡선 점을 통째로 내지 않는다.** 식마다 수백 점이라 대화가 그것으로 찬다 —
    # 고르는 데 필요한 것은 오차와 구간이다.
    fits = [
        {
            "family": one.get("family"),
            "label": one.get("label"),
            "relative_rmse": one.get("relative_rmse"),
            "r_squared": one.get("r_squared"),
            "max_residual": one.get("max_residual"),
            "fitted_range": [one.get("strain_min"), one.get("strain_max")],
            "parameters": [
                {
                    "name": two.get("name"),
                    "value": two.get("value"),
                    "unit": two.get("si_unit"),
                }
                for two in one.get("parameters") or []
            ],
            "notes": one.get("notes") or [],
        }
        for one in answer.get("fits") or []
    ]
    return {
        "sample_count": answer.get("sample_count"),
        "point_count": len(answer.get("source_points") or []),
        "fits": fits,
        "inherited": answer.get("elastic") or [],
        "notes": answer.get("notes") or [],
        "hint": (
            "**RMSE 가 가장 낮은 것을 자동으로 고르지 마라.** 적합 구간 밖에서 식들이"
            " 갈린다 — 후보를 사람에게 보이고 어디까지 쓸 것인지 물어라."
        ),
    }


@mcp.tool()
async def create_card_from_tests(
    ctx: Context,
    material_id: str,
    test_type: str,
    orientation: str,
    label: str,
    family: str | None = None,
    test_run_ids: list[str] | None = None,
    poisson_ratio: float | None = None,
    density: float | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """시험에서 나온 값으로 **물성 카드(초안)** 를 만든다.

    **기본이 미리보기(dry_run=True)다.** 그리고 카드는 **언제나 초안으로** 생긴다 —
    확정(publish)하는 도구는 안 냈다. 확정은 사람이 화면에서 한다.

    ## `preview_card_fit` 을 먼저 거쳐라

    식을 고르는 일은 이 도구가 하면 안 된다. 미리보기로 후보를 보이고 **사람이
    고른 식**을 `family` 로 넘겨라.

    **`family` 를 비우면 표만 저장한다.** 그것이 나쁜 선택이 아니다 — 많은 솔버가
    식보다 표를 그대로 받고, 식이 안 맞는 재료에서는 표가 더 정확하다. 사람이
    식을 안 골랐으면 비워 두고 그 사실을 말해라.

    ## 채우지 마라

    `poisson_ratio` 는 **인장시험이 주지 않는 값이다.** 모르면 비워 둔다 — 0.3 으로
    채우면 그것이 측정값인지 기본값인지 나중에 아무도 모른다. `density` 도 같다.

    `test_run_ids` 를 주면 그 시험들만 쓴다. 비우면 채택된 것 전부 — 카드는 자기가
    무엇으로 나왔는지 들고 있으므로(`source.test_run_ids`), 「10건짜리」와 「8건
    짜리」를 나란히 두고 견줄 수 있다.
    """
    body: dict[str, Any] = {
        "material_id": material_id,
        "test_type_key": test_type,
        "orientation": orientation,
        "test_run_ids": test_run_ids,
        "label": label,
        "family": family,
        "poisson_ratio": poisson_ratio,
        "density": density,
    }
    if dry_run:
        return {
            "dry_run": True,
            "will_create": {key: value for key, value in body.items() if value is not None},
            "note": (
                "이대로 만들려면 dry_run=False 로 다시 부르세요. **초안으로 생깁니다** —"
                " 확정은 사람이 화면에서 합니다."
                + ("" if family else " 식을 안 골랐으므로 표만 저장됩니다.")
            ),
        }
    made = await _send(ctx, "POST", "/fitting/cards", body)
    if isinstance(made, dict) and "error" not in made:
        made = dict(made)
        made["note"] = (
            "**초안으로 만들었습니다.** 덱으로 뽑아 볼 수는 있지만 덱 머리에"
            " 「초안」 이 박힙니다 — 확정은 사람이 화면에서 합니다."
        )
    return made


@mcp.tool()
async def create_declared_card(
    ctx: Context,
    material_id: str,
    label: str,
    synthesize_plastic: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """적어 둔 값만으로 **물성 카드(초안)** 를 만든다 — 시험이 없는 재료의 길.

    **언제나 초안(draft)으로 만들어진다.** 확정은 사람이 화면에서 한다 —
    확정된 카드로는 해석이 돌아가므로 그 결정을 AI 가 대신하지 않는다.

    `synthesize_plastic=True` 면 선언 스칼라(항복·인장·연신율)로 **소성 곡선을
    지어** 싣는다. 지어낸 표라는 사실이 카드 근거와 덱 각주에 남지만, 사람에게도
    반드시 그렇게 전한다.

    **기본이 미리보기(dry_run=True)다** — 무엇이 실릴지 먼저 본다.
    """
    preview = await _get(
        ctx,
        "/fitting/cards/declared/preview",
        {"material_id": material_id, "synthesize_plastic": synthesize_plastic},
    )
    if "error" in preview:
        return preview
    synthetic = preview.get("synthetic") or {}
    plan = {
        "material": preview.get("material_name"),
        "blocks": preview.get("blocks"),
        "values": [
            {"label": one.get("label"), "value_si": one.get("value"), "origin": one.get("source")}
            for one in preview.get("values", [])
        ],
    }
    if synthesize_plastic:
        if not synthetic.get("ok"):
            return {"error": f"소성 표를 합성할 수 없습니다: {synthetic.get('why')}"}
        plan["synthetic_plastic"] = {
            "model": synthetic.get("model"),
            "points": synthetic.get("points"),
            "caveat": f"합성 — 실측이 아니다. {synthetic.get('note')}",
        }
    if dry_run:
        plan["dry_run"] = True
        plan["note"] = "이대로 만들려면 dry_run=False 로 다시 부르세요. 카드는 초안으로 생깁니다."
        return plan

    made = await _send(
        ctx,
        "POST",
        "/fitting/cards/declared",
        {
            "material_id": material_id,
            "label": label,
            "synthesize_plastic": synthesize_plastic,
        },
    )
    if "error" in made:
        return made
    out = _card_summary(made)
    out["note"] = "초안으로 만들어졌다 — 확정은 사람이 화면에서 한다."
    return out

# ── 보강 (점검에서 드러난 누락) ───────────────────────────────────────────────


@mcp.tool()
async def list_cards(
    ctx: Context,
    material_id: str | None = None,
    status: str | None = None,
    limit: int = 20,
) -> dict[str, Any]:
    """물성 카드 목록 — 재료를 안 거치고 카드를 찾는다.

    `status` 는 `published`(확정) · `draft`(초안) · `deprecated`(중지). **확정된
    카드만 해석에 쓴다** — 초안은 만들어 본 것이지 결론이 아니다.

    `available_formats` 로 그 카드가 지금 낼 수 있는 덱 형식을 알 수 있다.
    """
    got = await _get(
        ctx,
        "/fitting/cards",
        {
            "material_id": material_id,
            "status": status,
            "limit": max(1, min(limit, MAX_LIMIT)),
        },
    )
    if "error" in got:
        return got
    return {
        "total": got.get("total", 0),
        "cards": [_card_summary(one) | {"material": one.get("material_name")}
                  for one in got.get("items", [])],
    }


@mcp.tool()
async def compare_catalog_materials(
    ctx: Context, catalog_material_ids: list[str]
) -> dict[str, Any]:
    """문헌 재료 여럿을 **한 표로 견준다**(최대 8종).

    물성마다 재료별 대표값이 한 줄로 오고, 값이 없는 칸은 빈 칸이다 — **빈 칸을
    0 으로 읽지 않는다**(그 재료에 그 물성 데이터가 없다는 뜻이다).

    각 칸의 `quality_tier` 와 `n_candidates`(후보 수)를 함께 본다 — tier 가 다른
    값을 나란히 놓고 「A 가 B 보다 크다」 고 말할 때는 그 사실을 밝힌다.
    """
    if not catalog_material_ids:
        return {"error": "재료 id 를 하나 이상 주세요."}
    got = await _get(ctx, "/catalog/compare", {"ids": ",".join(catalog_material_ids[:8])})
    if "error" in got:
        return got
    names = [one.get("name") for one in got.get("materials", [])]
    rows = []
    for row in got.get("rows", []):
        cells = []
        for cell in row.get("cells", []):
            value = cell.get("value_num")
            cells.append(
                None
                if value is None and not cell.get("value_text")
                else {
                    "value": value if value is not None else cell.get("value_text"),
                    "quality_tier": cell.get("quality_tier"),
                    "n_candidates": cell.get("n_candidates"),
                }
            )
        rows.append(
            {
                "property": row.get("name"),
                "property_key": row.get("property_key"),
                "unit": row.get("unit"),
                "values": cells,
            }
        )
    return {
        "materials": names,
        "note": "values 의 차례는 materials 차례와 같다. null 은 그 재료에 그 물성이 없다는 뜻이다.",
        "rows": rows,
    }


@mcp.tool()
async def measurement_gaps(ctx: Context) -> dict[str, Any]:
    """**우리가 못 재는 물성이 무엇인가** — 측정 능력의 빈 칸.

    카탈로그 물성 정의 전수를 훑어, 측정 능력이 이어진 것(`covered`)과 장비가
    하나도 없는 것(`gaps`)을 가른다. `owned_instrument_count` 가 0 이면 **장비
    카탈로그에는 있지만 우리는 못 잰다**는 뜻이다.

    응답이 길어지므로 빈 칸은 값이 많은 순으로 앞쪽만 낸다 — 전부 필요하면
    화면(측정법)에서 본다.
    """
    got = await _get(ctx, "/metrology/coverage")
    if "error" in got:
        return got
    covered = got.get("covered", [])
    gaps = got.get("gaps", [])
    not_owned = [one for one in covered if not one.get("owned_instrument_count")]
    gaps_sorted = sorted(gaps, key=lambda one: -(one.get("value_count") or 0))[:15]
    return {
        "covered_count": len(covered),
        "gap_count": len(gaps),
        "owned_none_count": len(not_owned),
        "gaps_top": [
            {
                "property": one.get("name"),
                "property_key": one.get("property_key"),
                "domain": one.get("domain"),
                "catalog_value_count": one.get("value_count"),
            }
            for one in gaps_sorted
        ],
        "covered_but_not_owned": [
            {"property": one.get("name"), "instruments_in_catalog": one.get("instrument_count")}
            for one in not_owned[:10]
        ],
        "note": (
            "gaps 는 장비 정보가 아예 없는 물성이고, covered_but_not_owned 는"
            " 장비는 알지만 우리가 보유하지 않은 물성이다 — 둘 다 「지금은 못 잰다」."
        ),
    }


@mcp.tool()
async def platform_summary(ctx: Context) -> dict[str, Any]:
    """플랫폼에 **무엇이 얼마나 있나** — 먼저 규모를 알고 시작한다.

    사내 재료·시험·카드, 문헌 카탈로그(재료·값·출처·등급 분포), 측정법(장비·
    보유)을 한 번에 센다.
    """
    catalog = await _get(ctx, "/catalog/summary")
    metrology = await _get(ctx, "/metrology/summary")
    materials = await _get(ctx, "/materials", {"limit": 1})
    runs = await _get(ctx, "/test-runs", {"limit": 1})
    cards = await _get(ctx, "/fitting/cards", {"limit": 1})
    out: dict[str, Any] = {}
    if isinstance(materials, dict) and "error" not in materials:
        out["materials"] = materials.get("total")
    if isinstance(runs, dict) and "error" not in runs:
        out["test_runs"] = runs.get("total")
    if isinstance(cards, dict) and "error" not in cards:
        out["cards"] = cards.get("total")
    if isinstance(catalog, dict) and "error" not in catalog:
        out["catalog"] = {
            "materials": catalog.get("materials"),
            "values": catalog.get("values"),
            "sources": catalog.get("sources"),
            "properties": catalog.get("definitions"),
            "tier_counts": catalog.get("tiers"),
        }
    if isinstance(metrology, dict) and "error" not in metrology:
        out["metrology"] = {
            "instruments_in_catalog": metrology.get("instruments"),
            "instruments_owned": metrology.get("instruments_owned"),
            "properties_covered": metrology.get("properties_covered"),
            "properties_total": metrology.get("properties_total"),
        }
    out["note"] = (
        "카탈로그 tier_counts 의 4 는 추정·가정값 수다 — 그 비중을 사람에게 말할 때"
        " 함께 밝힌다."
    )
    return out

# ── 리소스 (MaterialTwin 에서 — 도구 목록에 상주 비용을 안 얹는다) ─────────────


def max_limit(value: int) -> int:
    """상한을 강제한다. 도구 인자 이름이 `max` 라 내장 함수를 못 쓴다."""
    return MAX_LIMIT if value > MAX_LIMIT else (1 if value < 1 else value)


@mcp.tool()
async def resolve_property(ctx: Context, name: str) -> dict[str, Any]:
    """**물성 이름 → 물성 키.** 값을 묻기 전에 여기부터 거친다.

    사람이 부르는 말과 DB 의 키는 다르다. 한글·영문·기호·규격 표기가 다 들어오고
    (「항복강도」·「yield strength」·「Rp0.2」·「0.2% proof stress」), 비슷한
    이름의 **다른** 물성이 나란히 있다.

    ## 왜 이것부터인가 — 실측(2026-09-08)

        rheological.yield_stress    「항복응력」      9건   8 ~ 20 Pa      ← 유변학
        mechanical.yield_strength   「항복강도」    486건   0.1 ~ 2310 MPa  ← 금속

    이름이 정확히 「항복응력」 인 정의는 **페이스트가 흐르기 시작하는 응력**이다.
    사람이 「항복응력 200MPa」 를 물으면 금속의 항복강도를 뜻하는데, 이름만 맞춰
    고르면 9건짜리 엉뚱한 물성에 답하게 된다.

    ## `ambiguous` 가 참이면 고르지 말고 되물어라

    도메인이 다른 후보가 나란히 섰다는 뜻이다. 그때 하나를 골라 답하면 **조용히
    틀린 답**이 나간다 — 사용자에게 어느 쪽인지 물어라.

    `value_count` 가 0이면 그 물성으로는 아무것도 못 찾는다. `internal_items` 가
    있으면 사내에서 실제로 쓰는 물성이다.

    ## `parameterized` 가 참이면 **변수를 먼저 골라야 한다**

    한 이름에 변수 여럿이 들어 있다는 뜻이다 — 「Anand 점소성 상수」 하나에
    `A`(1/s)·`h0`(MPa)·`Q/R`(K) 등 9개가 있다. `terms` 에서 고른 것을
    `find_by_property(term=...)` 로 넘긴다. 안 고르고 값을 물으면 서로 다른
    단위의 숫자를 섞어서 답하게 되므로 서버가 거절한다.
    """
    got = await _get(ctx, "/catalog/properties/resolve", {"q": name})
    if "error" in got:
        return got
    if not got.get("candidates"):
        return {
            "query": name,
            "candidates": [],
            "hint": (
                f"'{name}' 로 물성을 찾지 못했습니다. `get_taxonomy` 로 어떤 물성 "
                "도메인이 있는지 보거나, 다른 이름으로 다시 물어보세요."
            ),
        }
    return got


@mcp.tool()
async def find_by_property(
    ctx: Context,
    property: str,
    unit: str,
    near: float | None = None,
    min: float | None = None,
    max: float | None = None,
    term: str | None = None,
    scope: str = "all",
    limit: int = 20,
) -> dict[str, Any]:
    """**값으로 재료를 찾는다** — 「항복응력이 200MPa 근처인 재료」.

    `property` 는 사람이 부르는 이름 그대로 준다(「항복응력」·「UTS」·「탄성계수」).
    서버가 `resolve_property` 와 같은 규칙으로 푼다.

    ## `unit` 은 필수다 — 짐작하지 마라

    값이 SI 로 저장돼 있어 200MPa 는 `200,000,000` 이다. 단위 없이 「200」 을
    걸면 **8 Pa 짜리가 나온다.** 사용자가 단위를 안 말했으면 **물어봐라** —
    문맥에서 짐작한 단위로 답하면 조용히 틀린다.

    ## 범위

        near=200          200 ±10% (180~220)
        min=180, max=220  그 사이

    ## 한 이름에 변수가 여럿인 물성이 있다

    「Anand 점소성 상수」 하나에 9개 상수가 들어 있다 — `A`(1/s)·`h0`(MPa)·
    `Q/R`(K) 처럼 **단위까지 제각각**이다. 그런 물성은 `term` 으로 어느 변수인지
    정해야 하고, 안 주면 서버가 변수 목록과 함께 거절한다(MNX-CATALOG-0034).

    `resolve_property` 의 `parameterized` 가 참이면 그런 물성이고, `terms` 에
    고를 것이 온다. **그때 `unit` 은 그 변수의 단위**여야 한다 — 이 값들은 SI 로
    저장돼 있지 않아 서버가 환산하지 않는다.

    ## 갈리면 값을 안 찾는다

    `ambiguous` 가 참으로 오면 `candidates` 만 온다 — 어느 물성인지 모른 채 찾은
    값은 **엉뚱한 물성의 정답**이다. 사용자에게 어느 쪽인지 물어라.

    ## 결과를 읽을 때

    `world` 가 `catalog` 면 문헌값, `internal` 이면 사내 재료의 선언 물성이다.
    `quality_tier` 는 문헌값의 등급이고 **tier4 도 걸러 내지 않는다**(추정·가정값도
    필요해서 모은 것이다) — 다만 답할 때 등급을 함께 말해라.
    `range_si` 로 실제로 건 범위를 되짚을 수 있다.
    """
    params: dict[str, Any] = {
        "q": property,
        "unit": unit,
        "term": term,
        "scope": scope,
        "limit": max_limit(limit),
    }
    if near is not None:
        params["near"] = near
    if min is not None:
        params["min"] = min
    if max is not None:
        params["max"] = max
    return await _get(ctx, "/catalog/properties/search", params)


@mcp.tool()
async def run_batch_processing(
    ctx: Context,
    test_run_ids: list[str],
    steps: list[dict[str, Any]] | None = None,
    recipe_key: str | None = None,
    adopt: bool = False,
    dry_run: bool = True,
) -> dict[str, Any]:
    """여러 시험에 같은 처리를 돌리고 **왜 안 됐는지를 묶어 준다.**

    이 도구의 값은 성공보다 **실패 쪽**에 있다. 50건을 돌리면 몇 건은 반드시
    실패하는데, 지금까지는 그것을 건별로 열어 봐야 했다. 여기서는 같은 사유끼리
    묶어 돌려주므로 **「12건은 점이 성겨서, 3건은 채널 이름이 달라서」** 처럼 한
    문장으로 옮길 수 있다.

    ## 채택은 기본이 꺼져 있다

    화면의 배치는 `adopt=True` 가 기본이다 — 사람이 이미 한 건으로 단계를 맞춰 본
    뒤에 누르기 때문이다. **AI 는 그 맞춰 보는 과정을 안 거쳤으므로** 여기서는
    꺼 둔다. 켜려면 사용자가 결과를 보고 말해야 한다.

    ## 실패를 고치려 들지 마라

    「점이 5개 미만」·「R² 가 낮다」 는 고장이 아니라 판단이다(`run_processing`
    설명 참조). 구간을 넓혀 다시 돌려 억지로 값을 뽑지 말고, **무엇이 왜 막혔는지**
    를 사람에게 옮겨라.
    """
    if not steps and not recipe_key:
        return {"error": "`steps` 또는 `recipe_key` 중 하나는 있어야 합니다."}
    if recipe_key and not steps:
        recipes = await _get(ctx, "/processing/recipes")
        if isinstance(recipes, dict) and "error" in recipes:
            return recipes
        found = next((one for one in recipes if one.get("key") == recipe_key), None)
        if found is None:
            return {"error": f"'{recipe_key}' 레시피를 찾지 못했습니다."}
        steps = found.get("steps") or []

    if dry_run:
        return {
            "dry_run": True,
            "will_run": {"count": len(test_run_ids), "recipe_key": recipe_key, "adopt": adopt},
            "note": (
                "이대로 돌리려면 dry_run=False 로 다시 부르세요. 결과는 불변으로 "
                "쌓이므로 기존 것을 덮지 않습니다."
            ),
        }

    answer = await _send(
        ctx,
        "POST",
        "/processing/batch",
        {
            "test_run_ids": test_run_ids,
            "steps": steps,
            "recipe_key": recipe_key,
            "adopt": adopt,
        },
    )
    if not isinstance(answer, dict) or "items" not in answer:
        if isinstance(answer, dict):
            return answer
        return {"error": "배치 응답을 읽지 못했습니다."}

    # **같은 사유끼리 묶는다.** 건별로 늘어놓으면 50줄이 되고, 그 50줄에서 사람이
    # 다시 패턴을 찾아야 한다 — 그 일을 여기서 한다.
    grouped: dict[str, list[str]] = {}
    for item in answer["items"]:
        if item.get("status") == "ok":
            continue
        reason = (item.get("error") or "이유 없음").strip()
        name = item.get("record_name") or str(item.get("test_run_id"))
        grouped.setdefault(reason, []).append(name)

    answer = dict(answer)
    answer["failures_by_reason"] = [
        {"reason": reason, "count": len(names), "runs": names[:10]}
        for reason, names in sorted(grouped.items(), key=lambda one: -len(one[1]))
    ]
    if grouped:
        answer["note"] = (
            f"{answer.get('failed')}건이 안 됐습니다. **사유별로 묶어 뒀습니다** — "
            "구간을 넓혀 다시 돌리지 말고, 무엇이 왜 막혔는지 사람에게 옮기세요."
        )
    return answer


@mcp.tool()
async def list_inbox(
    ctx: Context, status: str | None = None, limit: int = 20
) -> dict[str, Any]:
    """장비가 떨어뜨린 **아직 안 붙은 파일들** — 시험으로 등록할 후보.

    파일을 대화로 나르지 않아도 되는 길이다. 장비 PC 의 수집 에이전트가 파일을
    서버에 올려 두면, **어디에 붙일지만** 정하면 된다 — 사람이 화면에서 하는 일과
    같은 판단이다.

    `status` 로 좁힌다: `pending`(아직 안 붙음) · `assigned` · `approved`.
    """
    return await _get(
        ctx, "/pipelines/inbox", {"status": status, "limit": max_limit(limit)}
    )


@mcp.tool()
async def assign_inbox_item(
    ctx: Context, item_id: str, specimen_id: str, test_type: str, dry_run: bool = True
) -> dict[str, Any]:
    """인박스 파일을 **어느 시편의 어느 시험인지** 정해 준다.

    **기본이 미리보기(dry_run=True)다.**

    ## 무엇을 근거로 정하나

    파일 이름과 인박스 항목의 메타(장비·시각·조작자)가 단서다. 그것만으로 시편을
    확정할 수 없으면 **짐작하지 마라** — 「이 파일은 SECC_01__MD_02 로 보이는데
    맞습니까」 를 사람에게 물어라. 잘못 붙이면 그 곡선이 엉뚱한 재료의 물성이 되고,
    그 사실은 나중에 곡선을 열어 보기 전까지 안 드러난다.

    붙인 뒤에는 사람이 승인해야 시험이 된다(화면의 인박스). 승인 도구는 안 냈다 —
    그 판단은 사람의 것이다.
    """
    if dry_run:
        detail = await _get(ctx, f"/pipelines/inbox/{item_id}")
        return {
            "dry_run": True,
            "item": detail,
            "will_assign": {"specimen_id": specimen_id, "test_type": test_type},
            "note": (
                "이대로 붙이려면 dry_run=False 로 다시 부르세요. **시편이 맞는지 "
                "사람에게 확인받으세요** — 잘못 붙이면 엉뚱한 재료의 물성이 됩니다."
            ),
        }
    return await _send(
        ctx,
        "POST",
        f"/pipelines/inbox/{item_id}/assign",
        {"specimen_id": specimen_id, "test_type": test_type},
    )


@mcp.tool()
async def inspect_device_file(
    ctx: Context, sample_text: str, header_rows: int = 1
) -> dict[str, Any]:
    """장비 파일의 **앞부분을 글자로 보내** 구조를 읽는다 — 프로파일 짓기의 첫 걸음.

    파일을 통째로 나르지 마라. **앞 몇십 줄이면 구조는 다 드러난다** — 헤더·단위
    줄·구분자·열 이름. 20만 자를 넘으면 서버가 거절한다.

    `header_rows` 만 사람이 정한다. 헤더가 몇 줄인지는 기계가 알 수 없다 — 단위가
    둘째 줄에 오는 장비가 흔하니, 그런 파일이면 2 다.

    **이미 읽을 수 있는 파일이면 `matched_profile` 이 온다.** 그러면 새로 짓지 마라 —
    같은 장비에 프로파일이 둘이면 어느 것이 이겼는지 아무도 모르게 된다.
    """
    return await _send(
        ctx,
        "POST",
        "/formats/check",
        {"sample_text": sample_text, "header_rows": header_rows},
    )


@mcp.tool()
async def check_format_profile(
    ctx: Context,
    sample_text: str,
    definition: dict[str, Any],
    header_rows: int = 1,
    test_type: str | None = None,
    expect: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """지은 정의를 표본에 대고 **검사한다** — 저장하기 전에.

    ## 「돌아는 갔다」 로 끝내지 마라

    정의가 엉뚱해도 파싱은 성공할 수 있다. 이 파서는 **모든 열을 채널로 만들고**,
    `columns` 는 「이 열을 무슨 채널이라 부를까」 를 정할 뿐이다. 그래서 이름을 안
    정해 주면 원문 이름이 그대로 채널 키가 되고, **읽히기는 하는데 처리 단계가
    `force`·`displacement` 를 못 찾는다.**

    돌려주는 `checks` 를 하나씩 보고 실패한 것을 고쳐라:

        읽기                이 정의로 표본이 읽히나
        이름을 안 정한 열     규약 밖 이름이 될 열들
        필수 채널           `test_type` 을 주면 그 시험법 계약과 대조한다
        단위                단위를 못 읽은 채널
        기대값              `expect` 를 주면 하나씩 대조한다

    ## `test_type` 과 `expect` 를 되도록 주어라

    `test_type="tensile"` 을 주면 **그 시험법이 요구하는 채널이 다 붙었는지** 본다.
    이것이 이 검사에서 가장 값진 항목이다.

    `expect` 는 사람이 아는 답이다 — 「장비 화면에 최대하중이 12.34 kN 이라고
    떴다」 를 `{"summary": {"max_force": 12.34}}` 로 주면, 지은 정의가 같은 답을
    내는지 기계가 판정한다. **사용자에게 그 값을 물어보는 편이 낫다.**

    ## 단위 표기가 엄격해진다

    열에 이름을 정하는 순간 단위 검사가 엄격해진다 — 안 정하면 넘어가던 `C` 가
    「모르는 단위」 로 막힌다(`°C` 여야 한다). 그것도 이 검사가 잡아 준다.
    """
    return await _send(
        ctx,
        "POST",
        "/formats/check",
        {
            "sample_text": sample_text,
            "definition": definition,
            "header_rows": header_rows,
            "test_type": test_type,
            "expect": expect,
        },
    )


@mcp.tool()
async def save_format_profile(
    ctx: Context,
    key: str,
    label: str,
    test_type: str,
    definition: dict[str, Any],
    description: str | None = None,
    workspace: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """형식 프로파일을 저장한다 — **부서가 그 장비를 읽는 방법이 된다.**

    **`check_format_profile` 로 먼저 검사해라.** 검사 없이 저장하면 그 프로파일로
    올라온 시험의 곡선이 조용히 이상해지고, 그것은 나중에 찾기가 매우 어렵다.

    **기본이 미리보기(dry_run=True)다.**

    ## 화면이 못 고치는 정의를 지을 수 있다

    화면의 편집기는 정의의 일부만 다룬다 — 실측(2026-08-26)으로 드러난 함정이
    있다: 화면으로 만든 프로파일은 단위 칸을 못 넣어 **JSON 을 영영 못 읽었다.**
    AI 는 정의를 직접 짓기 때문에 그 한계가 없는데, **그러면 사람이 화면에서 고칠
    수 없는 프로파일이 생긴다.** 복잡한 정의를 지었으면 그 사실을 사용자에게
    말해라 — 「이건 화면에서 편집이 안 될 수 있습니다」.
    """
    body = {
        "key": key,
        "label": label,
        "test_type_key": test_type,
        "definition": definition,
        "description": description,
        "owner_workspace_slug": workspace,
        "is_active": True,
    }
    if dry_run:
        return {
            "dry_run": True,
            "will_save": body,
            "note": (
                "이대로 만들려면 dry_run=False 로 다시 부르세요. "
                "먼저 check_format_profile 로 검사했는지 확인하세요."
            ),
        }
    return await _send(ctx, "POST", "/formats", body)


@mcp.tool()
async def scan_deck_format(ctx: Context, deck_text: str) -> dict[str, Any]:
    """예제 **솔버 덱**을 읽어 내보내기 정의 초안을 만든다.

    덱을 붙이려는 사람에게는 대개 그 솔버의 덱 파일이 이미 있다. 구조는 서버가
    읽고 **「이 값이 무엇인가」 만 정하면 된다** — 장비 파일 정의가 같은 문제를
    이미 그렇게 풀었다.

    ## 고정폭 필드를 조심해라

    OptiStruct(8칸)·LS-DYNA(10칸)는 **칸 폭이 곧 값의 경계**다. 한 칸 어긋나면
    솔버가 다른 값을 읽는데 오류는 안 난다 — 조용히 틀린 해석이 된다. 초안에 폭이
    잡혀 오면 그대로 두고, 바꿀 때는 사용자에게 확인해라.
    """
    return await _send(
        ctx, "POST", "/fitting/export-profiles/scan", {"text": deck_text}
    )


@mcp.tool()
async def render_card_deck(
    ctx: Context, card_id: str, format: str, units: str | None = None
) -> dict[str, Any]:
    """물성 카드를 **덱 글자로 뽑는다** — 그대로 파일로 저장할 수 있는 본문.

    형식 목록은 `list_unit_systems` 가 아니라 `get_card` 의 `available_formats` 에
    있다.

    ## `units` 를 반드시 물어보고 넘겨라

    `units` 는 `list_unit_systems()` 의 key 다. **안 주면 SI 로 나간다.** 판재
    CAE 의 관행은 `mm·N·tonne` 이고 화면도 그 단위계라, SI 덱을 그대로 건네면
    받는 사람이 손으로 환산하게 된다 — **그 손이 사고의 자리다.**

    **네가 환산하지 마라.** 실측(2026-09-10): 이 인자가 없던 판에서 AI 가 SI 덱을
    받아 Pa→MPa 를 직접 고쳐 넣었다. 고정폭 필드에 손을 대는 일이고, 한 칸만
    어긋나도 솔버는 다른 값을 조용히 읽는다. 단위계는 여기서 넘겨 서버가 만들게
    한다.

    ## MID(재료 번호)를 사람에게 말해라

    덱 안의 재료 번호는 **그 파일 안에서만 뜻이 있는 수**다 — 카드 UUID 에서 만든
    것이라 전역으로 유일하지 않다. **덱 여럿을 손으로 합치면 겹칠 수 있고, 솔버는
    중복 MID 를 조용히 덮는다.**

    그 수는 **돌려주는 덱 글자 안에 있다**(솔버 재료 카드의 첫 칸). 따로 실어
    주지 않는 이유는 만드는 규칙이 백엔드에 있기 때문이다 — 여기서 다시 계산하면
    규칙이 두 벌이 되고, 그러면 언젠가 서로 다른 수를 말한다.

    덱을 건네줄 때 그것을 읽어 함께 말해라: 「이 덱의 MID 는 3847221 입니다.
    다른 덱과 합치실 거면 겹치는지 확인하세요.」 여러 재료를 한 덱으로 묶는
    자리(BOM 혼합 덱)는 서버가 중복을 막지만, 낱개로 뽑아 합칠 때는 사람이 본다.
    """
    deck = await _get_text(
        ctx, f"/fitting/cards/{card_id}/export", {"format": format, "units": units}
    )
    if isinstance(deck, dict):
        return deck  # 오류 봉투
    return {"format": format, "units": units or "si", "deck": deck}


@mcp.tool()
async def check_card_deck(
    ctx: Context,
    card_id: str,
    format: str,
    units: str | None = None,
    expect: dict[str, float] | None = None,
) -> dict[str, Any]:
    """뽑은 덱을 **되읽어 카드와 대조한다** — 건네기 전에.

    「돌아는 갔다」 와 「맞게 나왔다」 는 다르다. 덱은 **틀려도 오류 없이 돈다** —
    단위계를 잘못 고르거나 엉뚱한 카드를 집어도 파일은 멀쩡히 나온다.

        읽기        이 카드로 그 형식이 나오나 (안 나오면 왜)
        값          카드 값이 **그 단위계 숫자로** 덱에 있나
        표          마지막 점이 있나 (잘렸나)
        기대값       `expect` 를 주면 사람이 아는 값과 카드를 대조한다

    ## `expect` 는 SI 로 준다

    환산 자체가 검사 대상이라 **네가 환산하지 마라.** 「E 가 205 GPa 여야 한다」 는
    `{"elastic.youngs_modulus": 205e9}` 다. 사람에게 아는 값을 물어보는 편이 낫다 —
    그 답이 이 검사에서 가장 값진 항목이다.

    ## 각주를 반드시 읽어라

    `notes` 에 네킹·첫 점·합성 경고가 함께 온다. **검사가 다 통과해도 그 덱을
    그대로 쓰면 안 되는 경우가 있다** — 「첫 점이 항복점 값이 아닐 수 있습니다」 가
    그 예다. 그 문장을 사람에게 옮겨라.
    """
    return await _send(
        ctx,
        "POST",
        f"/fitting/cards/{card_id}/export/check",
        {"format": format, "units": units or "si", "expect": expect or {}},
    )


@mcp.tool()
async def draft_test_type(
    ctx: Context, key: str, label: str, channels: list[dict[str, Any]]
) -> dict[str, Any]:
    """새 시험법 **초안**을 만든다 — **저장하지 않는다.**

    시험 정의는 다른 둘과 성격이 다르다:

    - **검증할 방법이 없다.** 프로파일은 표본에 대 보면 되고 덱은 렌더해 보면
      되는데, 시험법은 만들어서 시험을 붙여 봐야 안다.
    - **되돌리기 어렵다.** 한번 시험이 붙기 시작하면 정의를 고칠 때 이미 붙은
      시험의 뜻이 바뀐다.
    - **채널 이름이 서버 계약이다.** 같은 이름은 같은 차원·단위여야 한다.

    그래서 이 도구는 **초안과 충돌 검사까지만** 한다. 저장은 사람이 화면에서
    한다 — 그 판단은 부서의 것이다.

    돌려주는 `conflicts` 를 반드시 사람에게 옮겨라: 같은 채널 이름이 다른 시험법에
    다른 단위로 이미 있으면, 그 이름을 쓰면 안 된다.
    """
    existing = await _get(ctx, "/test-types")
    if isinstance(existing, dict) and "error" in existing:
        return existing

    conflicts: list[dict[str, Any]] = []
    for one in existing:
        if one.get("key") == key:
            conflicts.append({"kind": "키 중복", "detail": f"'{key}' 시험법이 이미 있습니다."})
        for channel in one.get("channels") or []:
            for wanted in channels:
                if channel.get("key") != wanted.get("key"):
                    continue
                if channel.get("si_unit") != wanted.get("si_unit"):
                    conflicts.append(
                        {
                            "kind": "채널 단위 충돌",
                            "detail": (
                                f"'{channel['key']}' 는 '{one.get('key')}' 에서 "
                                f"{channel.get('si_unit')} 인데 {wanted.get('si_unit')} 로 "
                                "지으려 합니다 — 같은 이름은 같은 단위여야 합니다."
                            ),
                        }
                    )

    return {
        "draft": {"key": key, "label": label, "channels": channels},
        "conflicts": conflicts,
        "note": (
            "**저장하지 않았습니다.** 시험법은 검증할 방법이 없고 한번 시험이 붙으면 "
            "되돌리기 어렵습니다 — 이 초안을 사람에게 보이고, 화면(설정 → 시험 종류)"
            "에서 만들게 하세요."
            + (" 충돌을 먼저 해결해야 합니다." if conflicts else "")
        ),
    }


@mcp.tool()
async def list_recipes(ctx: Context, test_type: str | None = None) -> dict[str, Any]:
    """저장된 처리 레시피들 — **사람이 이미 합의해 둔 단계 묶음.**

    새로 지어내기 전에 여기부터 본다. 부서가 쓰는 레시피가 있으면 그것이 그 부서의
    합의이고, 다르게 돌린 결과는 견줄 수가 없다.
    """
    return _listed(await _get(ctx, "/processing/recipes", {"test_type": test_type}), "recipes")


@mcp.tool()
async def run_processing(
    ctx: Context,
    test_run_id: str,
    steps: list[dict[str, Any]] | None = None,
    recipe_key: str | None = None,
    source_curve_key: str | None = None,
    save: bool = False,
    retry: bool = False,
) -> dict[str, Any]:
    """시험 곡선에 처리를 돌린다. **기본은 저장하지 않는 미리보기다.**

    `steps` 를 직접 주거나 `recipe_key` 로 저장된 레시피를 쓴다. 저장하려면
    `save=True` — 그때도 **채택은 안 한다**(어느 결과를 공식으로 삼을지는 사람이
    정한다, ADR 0007).

    ## 실패는 실패다 — **임계값을 우회하지 마라**

    「점이 5개 미만이라 값을 안 냈다」 · 「그 구간의 R² 가 낮아 직선이 아니다」 는
    **고장이 아니라 판단이다.** 실측(2026-08-29): 18점짜리 곡선에서 탄성계수가
    1.83 GPa 로 나온 적이 있다 — 강판이면 200 GPa 다. 그 뒤로 못 믿을 값은 아예
    안 낸다.

    구간을 넓히거나 단계를 빼서 **억지로 값을 뽑지 마라.** 그렇게 나온 숫자는
    통계·물성 카드·해석 덱까지 그대로 흘러가고, 그것이 우회로 나온 값이라는 사실은
    어디에도 안 남는다. 못 냈으면 **왜 못 냈는지 사람에게 옮겨라.**

    ## `retry=True` — 사람이 켤 때만

    켜면 실패한 단계의 **구간·창을 한 번씩 넓혀 다시 시도**한다. 사람이 화면에서
    하는 것과 같은 조정이고, **임계값(최소 점 수·R² 문턱)은 코드 상수라 못 바꾼다** —
    방어선 자체는 내려가지 않는다.

    무엇을 바꿔 봤는지는 결과의 `attempts` 에 전부 남고, 저장하면 그 기록이 결과에
    함께 저장된다. **자동으로 켜지 마라** — 사용자가 「되는 데까지 해 봐」 라고
    말했을 때만 켠다.

    ## 결과를 읽을 때

    `problem` 이 있으면 거기까지만 돈 것이다 — 그 앞 단계의 곡선은 멀쩡하다.
    `notes` 에 경고가 있으면 값은 나왔지만 사람이 봐야 한다는 뜻이다(토우 R² 처럼
    재료에 따라 진짜로 직선이 아닐 수 있는 것들).
    """
    if not steps and not recipe_key:
        return {
            "error": (
                "`steps` 또는 `recipe_key` 중 하나는 있어야 합니다. "
                "`list_recipes` 로 부서가 쓰는 레시피부터 보세요."
            )
        }

    if recipe_key and not steps:
        recipes = await _get(ctx, "/processing/recipes")
        if isinstance(recipes, dict) and "error" in recipes:
            return recipes
        found = next((one for one in recipes if one.get("key") == recipe_key), None)
        if found is None:
            return {"error": f"'{recipe_key}' 레시피를 찾지 못했습니다."}
        steps = found.get("steps") or []

    body: dict[str, Any] = {
        "test_run_id": test_run_id,
        "steps": steps,
        "recipe_key": recipe_key,
        "source_curve_key": source_curve_key,
    }
    attempts: list[dict[str, Any]] = []
    answer = await _send(ctx, "POST", "/processing/preview", body)
    attempts.append({"steps": steps, "problem": (answer or {}).get("problem")})

    if retry and isinstance(answer, dict) and answer.get("problem"):
        for widened in retry_plan.widen(steps or []):
            body["steps"] = widened
            answer = await _send(ctx, "POST", "/processing/preview", body)
            attempts.append({"steps": widened, "problem": (answer or {}).get("problem")})
            if not (isinstance(answer, dict) and answer.get("problem")):
                break

    if isinstance(answer, dict) and "error" in answer:
        return answer
    if not isinstance(answer, dict):
        return {"error": "처리 응답을 읽지 못했습니다."}

    answer = dict(answer)
    if len(attempts) > 1:
        answer["attempts"] = attempts
        answer["note"] = (
            f"{len(attempts)}번 시도했습니다 — 구간을 넓혀 가며 다시 돌렸습니다. "
            "**사람에게 그 사실을 말하세요.** 첫 시도로 안 된 곡선입니다."
        )

    if not save:
        answer["dry_run"] = True
        answer.setdefault(
            "note", "저장하려면 save=True 로 다시 부르세요. 채택은 사람이 합니다."
        )
        return answer
    if answer.get("problem"):
        return {
            "error": f"처리가 끝까지 못 돌아 저장하지 않았습니다: {answer['problem']}",
            "attempts": attempts,
        }

    body["steps"] = attempts[-1]["steps"]
    saved = await _send(ctx, "POST", "/processing/results", body)
    if isinstance(saved, dict) and len(attempts) > 1:
        saved["attempts"] = attempts
    return saved


@mcp.tool()
async def save_recipe(
    ctx: Context,
    label: str,
    test_type: str,
    steps: list[dict[str, Any]],
    description: str | None = None,
    dry_run: bool = True,
) -> dict[str, Any]:
    """처리 레시피를 저장한다 — **부서가 함께 쓰는 단계 묶음이 된다.**

    **기본이 미리보기(dry_run=True)다.** 레시피는 한 사람의 설정이 아니라 그 부서의
    합의라, 만들기 전에 무엇이 저장될지 보여야 한다.

    새로 짓기 전에 `list_recipes` 로 이미 있는 것을 본다 — 비슷한 것이 있으면 그것을
    쓰는 편이 낫다. 레시피가 갈리면 같은 시험의 결과를 서로 못 견준다.
    """
    body = {
        "label": label,
        "test_type_key": test_type,
        "steps": steps,
        "description": description,
        "is_active": True,
    }
    if dry_run:
        return {
            "dry_run": True,
            "will_save": body,
            "note": "이대로 만들려면 dry_run=False 로 다시 부르세요.",
        }
    return await _send(ctx, "POST", "/processing/recipes", body)


@mcp.tool()
async def get_parameter_sets(ctx: Context, material_id: str) -> dict[str, Any]:
    """**이 재료가 가진 모델 파라미터 벌들** — Anand·Prony·Ogden 같은 것.

    여럿이 한 벌이어야 뜻이 있는 값이다(ADR 0029). `A` 만 떼어 보면 모델이 못 쓴다.

    ## 단위가 항마다 다르다

    한 벌 안에서 `1`·`1/s`·`MPa`·`K` 가 섞인다. **이 값들은 SI 가 아니라 그 항의
    원래 단위**이므로, 사람에게 옮길 때 단위를 반드시 함께 적어라 — 환산하지 마라.

    `source_ref` 가 어느 논문·자료의 벌인지 가리킨다. 같은 재료에 벌이 여럿이면
    **논문마다 값이 다르다는 뜻**이지 하나가 틀린 것이 아니다.
    """
    return _listed(await _get(ctx, f"/materials/{material_id}/parameter-sets"), "sets")


@mcp.tool()
async def get_catalog_parameter_sets(ctx: Context, catalog_material_id: str) -> dict[str, Any]:
    """문헌 재료가 가진 **모델 파라미터 벌들** — 사내로 받아 갈 후보.

    값 표(`get_catalog_material`)에는 이것들이 낱개로 흩어져 있다 — 「Anand 점소성
    상수」 라는 같은 이름이 아홉 번 선다. 여기서는 한 벌씩 묶어 준다.

    받아 가려면 `adopt_parameter_set` 를 쓴다.
    """
    return _listed(
        await _get(ctx, f"/catalog/materials/{catalog_material_id}/parameter-sets"), "sets"
    )


@mcp.tool()
async def adopt_parameter_set(
    ctx: Context,
    material_id: str,
    catalog_material_id: str,
    property_key: str,
    model: str = "",
    set_id: str = "",
    dry_run: bool = True,
) -> dict[str, Any]:
    """문헌의 파라미터 한 벌을 **사내 재료로 받아 온다.**

    **기본이 미리보기(dry_run=True)다** — 무엇이 담길지 먼저 보이고, 사람이 확인한
    뒤에 `dry_run=False` 로 다시 부른다.

    ## 한 벌이 통째로 간다

    `A` 만 골라 담을 수 없다. 모델이 9개를 함께 기대하기 때문이다.

    ## 벌이 여럿이면 골라야 한다

    같은 문헌 재료에 논문이 여럿이면 `model`·`set_id` 로 하나를 고른다 — 안 고르면
    서버가 목록과 함께 거절한다. **임의로 고르지 마라**: 논문이 다르면 값이 다르고,
    어느 쪽이 맞는지는 쓰는 사람의 판단이다.

    담긴 값은 그 재료의 물성 탭에 서고, 카드를 만들 때 인용할 수 있다.
    """
    sets = await _get(ctx, f"/catalog/materials/{catalog_material_id}/parameter-sets")
    if isinstance(sets, dict) and "error" in sets:
        return sets

    candidates = [
        one
        for one in sets
        if one.get("property_key") == property_key
        and (not model or one.get("model") == model)
        and (not set_id or one.get("set_id") == set_id)
    ]
    if not candidates:
        return {
            "error": (
                f"'{property_key}' 의 파라미터 벌을 그 문헌 재료에서 찾지 못했습니다. "
                "`get_catalog_parameter_sets` 로 무엇이 있는지 먼저 보세요."
            )
        }
    if len(candidates) > 1:
        return {
            "ambiguous": True,
            "candidates": [
                {
                    "model": one.get("model"),
                    "set_id": one.get("set_id"),
                    "quality_tier": one.get("quality_tier"),
                    "source": one.get("source_detail"),
                    "terms": [term.get("term") for term in one.get("terms") or []],
                }
                for one in candidates
            ],
            "note": (
                "벌이 여럿입니다 — `model` 또는 `set_id` 로 하나를 고르세요. "
                "논문이 다르면 값이 다릅니다. 어느 쪽인지 사용자에게 물어보세요."
            ),
        }

    chosen = candidates[0]
    if dry_run:
        return {
            "dry_run": True,
            "will_adopt": {
                "label": chosen.get("label"),
                "model": chosen.get("model"),
                "set_id": chosen.get("set_id"),
                "quality_tier": chosen.get("quality_tier"),
                "source": chosen.get("source_detail"),
                "terms": chosen.get("terms"),
            },
            "note": (
                "이대로 담으려면 dry_run=False 로 다시 부르세요. 같은 벌이 이미 "
                "있으면 갱신됩니다. 단위는 환산하지 않고 그대로 담깁니다."
            ),
        }

    return await _send(
        ctx,
        "POST",
        f"/materials/{material_id}/parameter-sets",
        {
            "property_key": property_key,
            "catalog_material_id": catalog_material_id,
            "model": chosen.get("model") or "",
            "set_id": chosen.get("set_id") or "",
        },
    )


@mcp.tool()
async def get_handbook_section(ctx: Context, section_id: str) -> dict[str, Any]:
    """**핸드북 절 하나를 펼쳐 읽는다.**

    `search_all` 이 절을 찾아 주지만 제목까지만 온다 — 본문을 읽으려면 여기다.
    찾은 결과의 `id` 를 그대로 넣는다(`kind` 가 `guide_section` 인 것).

    ## 규약이 여기 산다

    단위 규칙·시험 절차·판정 기준처럼 **사람이 합의해 적어 둔 것**이 핸드북이다.
    값을 계산해서 답하기 전에, 그 물성에 대한 절이 있는지 먼저 보는 편이 낫다 —
    거기 적힌 절차와 다르게 답하면 그것은 틀린 답이다.

    본문에 그림·표가 있으면 글로만 온다. 그림이 중요한 절은 화면에서 보라고 말해라.
    """
    return await _get(ctx, f"/guide/sections/{section_id}")


@mcp.tool()
async def search_all(
    ctx: Context,
    q: str,
    mode: str = "contains",
    kind: str | None = None,
) -> dict[str, Any]:
    """**한 칸으로 무엇이든 찾는다** — 이름·번호를 아는 게 없을 때 첫 손잡이.

    재료·시료·시편·시험·장비·문헌 물성·핸드북까지 한 번에 본다. 어느 종류인지
    모른 채 물어도 된다 — 그게 이 도구의 목적이다.

    ## 방식 셋

        exact      정확히 그 이름. 번호·코드를 알 때
        contains   그 말이 들어간 것 (기본)
        similar    오타·표기 흔들림 + **뜻이 가까운 것**

    `similar` 는 의미 검색이 켜져 있으면 뜻까지 본다 — 응답의 `meaning` 이 그것을
    말한다. **거짓이면 글자만 본 것이다**: 못 찾았을 때 「그런 자료가 없다」 고
    단정하지 말고, 뜻 검색이 꺼져 있었다고 함께 말해라.

    ## 결과를 읽을 때

    `matched` 가 왜 걸렸는지다 — `exact` · `prefix` · `contains` · `similar`(글자가
    비슷) · `meaning`(뜻이 가까움) · `both`. **`meaning` 으로만 걸린 것은 낱말이
    하나도 안 겹친다** — 사람에게 옮길 때 그 점을 밝혀라.

    `kind` 로 한 종류만 좁히면 더 많이 준다. 종류 목록은 `get_ontology` 에 있고,
    거기서 나온 `id` 로 `related`·`find_path` 를 이어 부를 수 있다.
    """
    return await _get(ctx, "/search", {"q": q, "mode": mode, "kind": kind})


@mcp.tool()
async def get_ontology(ctx: Context) -> dict[str, Any]:
    """**이 시스템의 지도** — 무엇이 있고 무엇이 무엇과 이어지나.

    길을 찾기 전에 여기부터 봐라. 사람은 화면에서 링크를 눌러 다니지만 너에게는
    링크가 없다 — 이 응답이 지도의 전부다.

    ## 읽는 법

        kinds       마디 종류. `material`·`property`·`instrument` …
        relations   사이. `src` 에서 `dst` 로 `label` 을 읽는다

    `source` 는 그 관계가 DB 어디에 실려 있나다(`fk:…` · `table:…`). **답에 옮길
    필요는 없다** — 네가 「이 길이 진짜 있나」 를 판단할 근거다.

    이 지도의 종류·관계 이름을 그대로 `related` 와 `find_path` 에 넣어라. 지도에
    없는 이름을 지어내면 422 로 돌아온다.
    """
    return await _get(ctx, "/ontology")


@mcp.tool()
async def related(
    ctx: Context,
    kind: str,
    id: str,
    relation: str | None = None,
    direction: str = "both",
    depth: int = 1,
) -> dict[str, Any]:
    """**이 마디 옆에 무엇이 있나** — 관계 이름과 함께 온다.

    `kind` 와 `id` 는 `get_ontology` 의 종류와 그 마디의 식별자다. **`property`
    만 식별자가 문자열 키**다(`mechanical.yield_strength`) — `resolve_property`
    가 돌려주는 `key` 를 그대로 쓴다.

    ## `counts` 를 먼저 봐라

    관계별 이웃 수가 함께 온다. **0인 관계는 안 실린다** — 거기 없는 관계로 더
    파고들지 마라. 없는 것을 「없다」 고 답하는 편이 낫다.

    ## 깊이

    `depth=1` 이 기본이고 3까지다. 넓히기 전에 `counts` 로 크기를 가늠해라 —
    `truncated` 가 참이면 상한에서 잘린 것이고, 그때 답에 「일부만 봤다」 를
    밝혀라.

    ## 안 보이는 것은 안 온다

    권한 밖의 마디에서는 **길이 끊긴다.** 「이어져 있는데 이름만 가려진 것」이
    아니라 아예 없는 것처럼 온다 — 그러니 「자료가 없다」 와 「권한이 없다」 를
    구분해서 단정하지 마라.
    """
    return await _get(
        ctx,
        "/ontology/related",
        {
            "kind": kind,
            "id": id,
            "relation": relation,
            "direction": direction,
            "depth": 1 if depth < 1 else (3 if depth > 3 else depth),
        },
    )


@mcp.tool()
async def find_path(
    ctx: Context,
    from_kind: str,
    from_id: str,
    to_kind: str,
    to_id: str,
    max_depth: int = 4,
) -> dict[str, Any]:
    """**이 둘이 어떻게 이어지나** — 「이 값이 어느 재료에서 나왔나」.

    사슬을 모를 때 쓴다. 가장 짧은 길 하나가 `steps` 로 온다:

        tested → part_of → derived_from        시험 → 시편 → 시료 → 재료

    `found` 가 거짓이면 **길이 없는 것이다.** 지어내지 마라 — 양끝이 실제로 안
    이어져 있거나, 가운데 마디를 볼 권한이 없다. `note` 에 그렇게 적혀 온다.
    """
    return await _get(
        ctx,
        "/ontology/path",
        {
            "from_kind": from_kind,
            "from_id": from_id,
            "to_kind": to_kind,
            "to_id": to_id,
            "max_depth": 1 if max_depth < 1 else (6 if max_depth > 6 else max_depth),
        },
    )


@mcp.resource("matnexus://guide", mime_type="text/markdown")
def guide_resource() -> str:
    """MatNexus 사용 규약 — 단위·값의 무게·층·흐름."""
    try:
        return GUIDE_PATH.read_text(encoding="utf-8")
    except OSError as failed:
        return f"안내 문서를 읽지 못했습니다: {failed}"


@mcp.tool()
async def get_taxonomy(ctx: Context) -> str:
    """재료 분류 체계와 **지금 DB 의 분포** — 무엇으로 좁힐 수 있는지 안다.

    라이브다. 화면의 필터가 쓰는 것과 같은 값이라, 여기 없는 분류로 좁히면
    아무것도 안 나온다.

    **리소스가 아니라 도구인 이유**(실측 2026-09-06): MCP 2.x 는 URI 템플릿이
    없는 정적 리소스에 Context 를 주입하지 않는다 — 그러면 호출자의 토큰을 못
    날라 401 이 된다. 분포는 로그인해야 보이는 자료라 도구여야 한다.
    """
    data = await _get(ctx, "/catalog/summary")
    if "error" in data:
        return data["error"]
    lines = ["# 재료 분류와 분포", "", "## 문헌 카탈로그", ""]
    for name, rows in (
        ("분류(category)", data.get("categories") or {}),
        ("계통(subsystem)", data.get("subsystems") or {}),
        ("물성 도메인", data.get("domains") or {}),
    ):
        lines.append(f"### {name}")
        for key, count in sorted(rows.items(), key=lambda one: -one[1])[:12]:
            lines.append(f"- {key or '(미분류)'}: {count}")
        lines.append("")
    tiers = data.get("tiers") or {}
    if tiers:
        lines += ["### 품질 등급 분포", ""]
        for key in sorted(tiers):
            lines.append(f"- tier {key}: {tiers[key]}")
        lines.append("")
        lines.append("tier 4 는 계산·추정·가정이다 — 실측처럼 옮기지 않는다.")
    return "\n".join(lines)


# ── 프롬프트 (MaterialTwin 에서 — 「무엇부터 물어야 하나」) ────────────────────


@mcp.prompt()
def pick_material(requirement: str) -> str:
    """요구조건에 맞는 재료 고르기 — 후보 찾기부터 근거 확인까지."""
    return (
        f"요구조건: {requirement}\n\n"
        "다음 차례로 진행하세요.\n"
        "1. get_guide() 로 값의 무게 규약(origin·tier·caveat)을 먼저 확인합니다.\n"
        "2. 사내에 이미 있는지 봅니다 — search_materials 로 찾고, 있으면\n"
        "   get_material 로 선언 물성과 카드를 확인합니다. **실측이 있으면\n"
        "   실측이 먼저입니다.**\n"
        "3. 없거나 모자라면 search_catalog 로 문헌 후보를 찾고,\n"
        "   compare_catalog_materials 로 나란히 견줍니다.\n"
        "4. 고른 값의 quality_tier 와 출처를 **반드시 함께** 보고합니다 —\n"
        "   tier 4 는 추정이고, 그 사실을 빼고 말하면 그 값으로 해석이 돌아갑니다.\n"
        "5. 그 물성을 직접 재야 한다면 how_to_measure 로 장비 보유 여부를 봅니다."
    )


@mcp.prompt()
def build_deck_for_bom(bom: str) -> str:
    """부품표로 해석용 덱 만들기 — 매칭부터 단위계까지."""
    return (
        f"부품표:\n{bom}\n\n"
        "다음 차례로 진행하세요.\n"
        "1. match_bom 으로 문헌 후보를 봅니다. **후보가 애매하면 임의로 고르지\n"
        "   말고 사람에게 확인합니다.**\n"
        "2. 사내 실측 카드가 있는 부품은 그것을 씁니다 — search_materials →\n"
        "   get_material 로 카드 id 를 찾아 card_id 로 넘깁니다.\n"
        "3. list_unit_systems 로 단위계를 고릅니다. 받는 쪽 해석 모델이 mm·tonne\n"
        "   계인지 반드시 사람에게 물어봅니다 — 계가 섞이면 조용히 1000배\n"
        "   틀립니다.\n"
        "4. build_deck 으로 만들고, 건너뛴 부품과 합성 곡선 수를 그대로\n"
        "   보고합니다. 합성이 있으면 「실측이 아니다」 를 반드시 말합니다."
    )


def main() -> None:
    """기동. **기본은 127.0.0.1 이고, 밖에 열 때는 허용 Host 를 반드시 받는다.**

    ReportArchive 는 비-localhost 바인딩인데 허용 목록이 비면 **DNS rebinding
    보호를 껐다**(사내망 전제). 우리는 반대로 한다 — 목록 없이 밖에 열려고 하면
    거절하고 이유를 말한다. 조용히 보호를 끄는 기본값은 두지 않는다.
    """
    if os.environ.get("MATNEXUS_MCP_TRANSPORT", "streamable-http") == "stdio":
        mcp.run(transport="stdio")
        return

    host = os.environ.get("MATNEXUS_MCP_HOST", "127.0.0.1")
    allowed = [
        one.strip()
        for one in os.environ.get("MATNEXUS_MCP_ALLOWED_HOSTS", "").split(",")
        if one.strip()
    ]
    if host not in ("127.0.0.1", "localhost") and not allowed:
        raise SystemExit(
            f"MATNEXUS_MCP_HOST={host} 로 밖에 열려면 MATNEXUS_MCP_ALLOWED_HOSTS 를"
            " 함께 주세요(쉼표로 구분). 허용 Host 없이 열면 DNS rebinding 보호가"
            " 무의미해집니다."
        )
    mcp.run(
        transport="streamable-http",
        host=host,
        port=int(os.environ.get("MATNEXUS_MCP_PORT", "8012")),
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=allowed or ["127.0.0.1:*", "localhost:*"],
        ),
    )


if __name__ == "__main__":
    main()
