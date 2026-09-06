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

# ── 리소스 (MaterialTwin 에서 — 도구 목록에 상주 비용을 안 얹는다) ─────────────


@mcp.resource("matnexus://guide", mime_type="text/markdown")
def guide_resource() -> str:
    """MatNexus 사용 규약 — 단위·값의 무게·층·흐름."""
    try:
        return GUIDE_PATH.read_text(encoding="utf-8")
    except OSError as failed:
        return f"안내 문서를 읽지 못했습니다: {failed}"


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
