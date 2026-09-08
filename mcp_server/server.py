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
        try:
            body = got.json()["error"]
            return {"error": f"{body.get('message')} ({body.get('code')})"}
        except Exception:
            return {"error": f"요청이 실패했습니다(HTTP {got.status_code})."}
    return got.json()


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
        try:
            body_json = got.json()["error"]
            return {"error": f"{body_json.get('message')} ({body_json.get('code')})"}
        except Exception:
            return {"error": f"요청이 실패했습니다(HTTP {got.status_code})."}
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
    `overview` · `units` · `trust` · `layers` · `workflow` · `limits`.
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
    ctx: Context, catalog_material_id: str, domain: str | None = None
) -> dict[str, Any]:
    """문헌 재료 하나의 **물성 전부** — 값·조건·등급·출처.

    같은 물성에 값이 여럿이면 **대표값이 먼저** 오고 밀린 후보도 이유와 함께
    온다(`representative`·`separated_by`). 값이 많은 재료는 `domain` 으로 좁혀라
    (`mechanical`·`thermal`·`physical`·`electrical`·`optical` …).

    **tier 4 는 추정·가정이다.** `caveat` 가 붙은 값을 실측처럼 옮기지 않는다.
    """
    got = await _get(ctx, f"/catalog/materials/{catalog_material_id}")
    if "error" in got:
        return got
    values = [
        _catalog_value(row)
        for row in got.get("values", [])
        if not domain or row.get("domain") == domain
    ]
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
        "shown_values": len(values),
        "tier_counts": tiers,
        "values": values,
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


@mcp.tool()
async def build_deck(
    ctx: Context,
    rows: list[dict[str, Any]],
    units: str | None = None,
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
    그렇게 전해야 한다. 기본은 끄여 있다.
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
        # **덱 본문을 통째로 내지 않는다.** 수백 줄이면 대화가 그것으로 찬다 —
        # 머리(출처 각주)만 보이고, 파일이 필요하면 화면에서 받는다.
        "header": "\n".join(
            line for line in text.splitlines()[:40] if line.startswith(("$", "*"))
        ),
        "note": (
            "덱 본문은 화면(카드 → BOM 혼합 덱)에서 받는다. 여기서는 무엇이"
            " 실렸는지와 출처 각주만 본다."
        ),
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
