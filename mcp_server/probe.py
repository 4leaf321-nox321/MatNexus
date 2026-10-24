"""도구 전부를 **진짜 MCP 클라이언트로 한 번씩 불러 본다.**

## 왜 필요한가 (실측 2026-09-10)

도구 41개를 만들어 놓고 한 번도 MCP 로 불러 본 적이 없었다. 처음 불러 보자
**넷이 죽어 있었다** — 그런데 같은 엔드포인트를 curl 로 부르면 전부 멀쩡했다.
MCP 로만 드러나는 층이 있기 때문이다:

    반환 표기와 실제 모양      mcp 2.x 는 결과를 `-> dict` 로 검증한다(1.x 는 안 했다).
                             목록 엔드포인트를 그대로 흘리면 도구가 통째로 죽는다.
    JSON 이 아닌 응답          덱은 text/plain 이라 `.json()` 에서 터졌다.
    오류의 자세한 내용          「건너뛴 이유를 보세요」 인데 이유가 안 실려 있었다.

셋 다 **HTTP 로는 안 보인다.** 그래서 이 파일이 있다.

## 어떻게 돌리나

백엔드가 떠 있어야 하고(개발 8011), 개인 토큰이 필요하다. 서버는 이 스크립트가
자식 프로세스로 띄웠다가 끝나면 내린다 — 따로 띄워 둘 것 없다.

    $env:MATNEXUS_PAT = 'mnx_pat_...'
    $env:MATNEXUS_API_BASE = 'http://127.0.0.1:8011/api'
    .\.venv\Scripts\python.exe probe.py

CI 에는 안 넣는다 — 살아 있는 DB 와 그 안의 자료에 기대기 때문이다. 대신
`backend/tests/architecture/test_mcp_tools.py` 가 위 세 함정 중 첫째를 정적으로
막는다. 나머지 둘은 여기서만 잡힌다.

## 쓰기는 전부 미리보기다

`dry_run=True` 로만 부른다. 이 스크립트는 아무것도 바꾸지 않는다 — 개발 DB 라도
점검이 자료를 남기면 다음 점검이 그것을 보고 판단하게 된다.

**미리보기가 없는 쓰기는 일부러 거절당하게 부른다**(2026-09-25) — 없는 id, 카탈로그에
없는 분류값. 서버는 쓰기 전에 거절한다. 그래도 도구가 서버까지 가서 그 거절을 그대로
돌려주는지가 이 파일이 보는 층이다. 전에는 문헌 카탈로그 쓰기 여섯이 **한 번도 안
불렸다**(「부르지 못한 도구」). 이런 호출은 `expect_error` 로 부르고, 거절돼야 성공으로
센다 — 뜻밖에 통과하면 무언가 쓰였다는 뜻이라 문제로 센다.
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.shared._httpx_utils import create_mcp_http_client

HERE = Path(__file__).resolve().parent
PORT = int(os.environ.get("MATNEXUS_PROBE_PORT", "8013"))
API_BASE = os.environ.get("MATNEXUS_API_BASE", "http://127.0.0.1:8011/api")

#: 인장 장비가 내는 모양을 줄인 것. 온도 단위가 `°C` 인 것이 중요하다 — 열에
#: 채널 이름을 정해 주면 단위 검사가 엄격해져서 `C` 는 막힌다.
SAMPLE = (
    "Time;Displacement;Force;Temperature\n"
    "s;mm;kN;°C\n"
    "0.0;0.000;0.00;23.1\n"
    "0.1;0.050;1.20;23.1\n"
    "0.2;0.100;2.45;23.2\n"
    "0.3;0.150;3.60;23.2\n"
)
DEFINITION: dict[str, Any] = {
    "columns": {
        "Time": {"channel": "time"},
        "Displacement": {"channel": "displacement"},
        "Force": {"channel": "force"},
        "Temperature": {"channel": "temperature"},
    }
}

results: list[dict[str, Any]] = []


async def call(
    session: ClientSession,
    name: str,
    args: dict[str, Any] | None = None,
    *,
    expect_error: bool = False,
) -> Any:
    """한 번 부르고 결과를 적는다. **오류도 200 으로 온다** — 본문을 봐야 안다.

    `expect_error` 는 **거절당해야 맞는** 호출이다(미리보기가 없는 쓰기를 무해하게 부를
    때). 그때는 거절이 성공이고, 통과가 문제다."""
    started = time.perf_counter()
    try:
        out = await session.call_tool(name, args or {})
    except Exception as exc:  # 프로토콜이 깨진 것 — 이것이 진짜 실패다
        results.append({"tool": name, "ok": False, "excerpt": f"[예외] {exc}"})
        print(f"!! {name}  [예외] {exc}")
        return None

    if out.structured_content:
        body = json.dumps(out.structured_content, ensure_ascii=False)
    else:
        body = " ".join(getattr(one, "text", str(one)) for one in out.content or [])
    took = round((time.perf_counter() - started) * 1000)
    refused = bool(out.is_error) or '"error"' in body[:400]
    bad = not refused if expect_error else refused
    results.append({"tool": name, "ok": not bad, "ms": took, "excerpt": body[:220]})
    mark = "!! " if bad else ("OK(거절) " if expect_error else "OK ")
    print(mark + f"{name}  {took}ms  " + " ".join(body[:130].split()))
    try:
        return json.loads(body)
    except Exception:
        return body


def _first(payload: Any, *keys: str) -> str | None:
    """응답 모양이 도구마다 달라서 흔한 자리를 차례로 뒤진다."""
    if isinstance(payload, dict):
        if isinstance(payload.get("groups"), list):
            for group in payload["groups"]:
                got = _first(group, *keys)
                if got:
                    return got
        for key in (
            "items",
            "materials",
            "results",
            "rows",
            "cards",
            "runs",
            "hits",
            "recipes",
        ):
            if isinstance(payload.get(key), list) and payload[key]:
                return _first(payload[key][0], *keys)
        for key in keys:
            if payload.get(key):
                return str(payload[key])
    if isinstance(payload, list) and payload:
        return _first(payload[0], *keys)
    return None


async def sweep(session: ClientSession) -> None:
    listed = await session.list_tools()
    names = sorted(one.name for one in listed.tools)
    print(f"도구 {len(names)}개 등록됨\n")

    await call(session, "get_guide")
    await call(session, "get_guide", {"topic": "units"})
    await call(session, "platform_summary")
    await call(session, "get_taxonomy")
    await call(session, "measurement_gaps")

    found = await call(session, "search_materials", {"query": "A", "limit": 3})
    material_id = _first(found, "id", "material_id")
    await call(session, "search_all", {"q": "강", "mode": "contains", "limit": 5})
    await call(session, "search_all", {"q": "강판", "mode": "similar", "limit": 3})
    await call(session, "resolve_property", {"name": "항복강도"})
    await call(session, "get_property_classification")
    await call(session, "get_property_classification", {"field": "mechanical"})
    # 미리보기(기본) — 아무것도 안 넣는다. 「항복응력」 은 유변학 물성이라 cross_domain 에 선다.
    await call(
        session,
        "classify_properties",
        {
            "rows": [
                {"field": "기계", "group": "강도", "property": "mechanical.yield_strength"},
                {"field": "기계", "group": "강도", "property": "항복응력"},
            ]
        },
    )
    # SP 코어(ADR 0063) — 받아 둔 것이 없어도 무해하게 끝나는 길만. 잇기 · 끊기 · 받기는
    # 미리보기, 없는 타입 · 없는 연결은 서버가 거절해야 맞다.
    await call(session, "sp_core_status")
    await call(session, "find_sp_core_objects", {"q": "점검"})
    await call(
        session,
        "match_sp_core",
        {"sp_type": "없는-타입-점검", "target": "property"},
        expect_error=True,
    )
    await call(
        session,
        "link_sp_core",
        {
            "items": [
                {
                    "sp_type": "없는-타입-점검",
                    "sp_key": "x",
                    "target": "property",
                    "target_ref": "mechanical.yield_strength",
                }
            ]
        },
        # 없는 타입이라 미리보기가 그 줄을 `status: error` 로 세운다 — 그것이 맞는 답이다.
        expect_error=True,
    )
    await call(session, "unlink_sp_core", {"link_ids": [str(uuid.uuid4())]})
    await call(session, "sync_sp_core")
    await call(
        session, "find_by_property", {"property": "yield_strength", "unit": "MPa", "min": 100}
    )

    if material_id:
        detail = await call(session, "get_material", {"material_id": material_id})
        # **이름으로도 받는지** 본다(2026-09-18). uuid 만 받던 시절에는 AI 가 이름을
        # 넣고 거절당해 검색으로 한 번 더 돌았다 — 기준선 3차가 두 번 걸렸다.
        name = (detail or {}).get("name") if isinstance(detail, dict) else None
        if name:
            await call(session, "get_material", {"material_id": name})
        # 이 재료가 쓰인 부품(2026-10-25) — 없으면 빈 목록이 맞는 답이다.
        await call(session, "list_material_parts", {"material_id": material_id, "limit": 5})
        # 문헌 연결 — 후보를 보고, 있으면 첫 후보로 **미리보기만**(2026-10-08).
        linking = await call(session, "link_catalog_material", {"material_id": material_id})
        offered = (linking or {}).get("candidates") if isinstance(linking, dict) else None
        if offered:
            await call(
                session,
                "link_catalog_material",
                {
                    "material_id": material_id,
                    "catalog_material_id": str(offered[0]["catalog_material_id"]),
                    "dry_run": True,
                },
            )
        samples = await call(session, "list_samples", {"material_id": material_id})
        rows = (samples or {}).get("samples") if isinstance(samples, dict) else None
        if rows:
            await call(session, "get_sample", {"sample_id": rows[0]["id"]})
            # 등록 — **미리보기로만.** 기존 재료의 분류를 그대로 되돌려 넣어
            # 기준정보 문(ADR 0032)에 안 걸리게 한다. 지어낸 등급을 넣으면
            # 프로브가 매번 「막혔다」 만 확인하게 된다.
            await call(
                session,
                "create_sample",
                {
                    "material_id": material_id,
                    "lot_no": "PROBE-LOT",
                    "dry_run": True,
                },
            )
            await call(
                session,
                "create_specimen",
                {"sample_id": rows[0]["id"], "orientation": "MD", "dry_run": True},
            )
        classified = (detail or {}).get("classification") if isinstance(detail, dict) else None
        if isinstance(classified, dict) and classified.get("grade"):
            await call(
                session,
                "create_material",
                {
                    "family": classified.get("family"),
                    "category": classified.get("category"),
                    "grade": classified.get("grade"),
                    "details": "PROBE",
                    "dry_run": True,
                },
            )
        await call(session, "list_groups", {"material_id": material_id})
        await call(session, "property_coverage", {"material_id": material_id})
        await call(session, "deck_readiness", {"material_id": material_id})
        await call(session, "get_parameter_sets", {"material_id": material_id})
        await call(session, "get_statistics", {"material_id": material_id})
        await call(session, "compare_material_statistics", {"material_ids": [material_id]})

    # ── 분포·스펙 갭·흩어짐 — **채택된 통계가 있는 재료**에서만 뜻이 있다 ─────
    await call(session, "spec_gap", {"limit": 5})
    await call(session, "spread_by_group", {"group_by": "family"})
    stats_material = None
    picked = await call(session, "search_materials", {"query": "SCATTER", "limit": 3})
    for candidate in (picked or {}).get("materials", []) if isinstance(picked, dict) else []:
        stats = await call(session, "get_statistics", {"material_id": candidate["id"]})
        groups = (stats or {}).get("groups") if isinstance(stats, dict) else None
        if groups:
            stats_material = (candidate["id"], groups[0])
            break
    if stats_material:
        sid, group = stats_material
        keys = await call(
            session,
            "get_distribution",
            {
                "material_id": sid,
                "test_type": group["test_type"],
                "orientation": group["orientation"],
            },
        )
        rows = (keys or {}).get("distributable") if isinstance(keys, dict) else None
        if rows:
            await call(
                session,
                "get_distribution",
                {
                    "material_id": sid,
                    "test_type": group["test_type"],
                    "orientation": group["orientation"],
                    "scalar_key": rows[0]["key"],
                    "bootstrap": 50,
                },
            )
    # 환산은 서버가 — 오프셋(°C)·접두어 조합(W/(mm*K))·기본 SI 세 갈래를 다 본다.
    await call(session, "convert_unit", {"value": 300, "from_unit": "MPa", "to_unit": "kgf/mm2"})
    await call(session, "convert_unit", {"value": 25, "from_unit": "°C"})
    await call(session, "convert_unit", {"value": 1, "from_unit": "W/(mm*K)"})
    await call(session, "list_condition_fields", {"test_type": "tensile"})
    systems = await call(session, "list_unit_systems")
    unit_key = None
    if isinstance(systems, dict):
        rows = systems.get("systems") or []
        # SI 가 아닌 계를 하나 고른다 — **환산이 실제로 먹는지** 보려는 것이라
        # 기본값(SI)으로는 확인이 안 된다.
        unit_key = next(
            (one.get("key") for one in rows if one.get("key") and one["key"] != "si"), None
        )
    await call(session, "list_card_blocks")
    await call(session, "list_processing_steps", {"test_type": "tensile"})
    specimens = await call(session, "list_specimens", {"limit": 2})
    specimen_id = None
    if isinstance(specimens, dict) and specimens.get("specimens"):
        specimen_id = specimens["specimens"][0].get("id")
    if specimen_id:
        # 다른 두께로 옮기기 — **미리보기만**(계획을 받는다, 쓰지 않는다).
        await call(
            session,
            "relocate_specimens",
            {"specimen_ids": [specimen_id], "spec_thickness": 9.87, "dry_run": True},
        )
    cards = await call(session, "list_cards", {"limit": 3})
    card_id = _first(cards, "id", "card_id")
    if card_id:
        card = await call(session, "get_card", {"card_id": card_id})
        formats = card.get("available_formats") or [] if isinstance(card, dict) else []
        if formats:
            await call(session, "render_card_deck", {"card_id": card_id, "format": formats[0]})
            if unit_key:
                await call(
                    session,
                    "render_card_deck",
                    {"card_id": card_id, "format": formats[0], "units": unit_key},
                )
                # **뽑은 것을 되읽어 본다.** 이 검사 자체가 도는지도 봐야 한다.
                await call(
                    session,
                    "check_card_deck",
                    {"card_id": card_id, "format": formats[0], "units": unit_key},
                )

    catalog = await call(session, "search_catalog", {"query": "steel", "limit": 3})
    catalog_id = _first(catalog, "id")
    listed_catalog = (
        catalog.get("materials") or catalog.get("items") or []
        if isinstance(catalog, dict)
        else []
    )
    catalog_ids = [
        one["id"] for one in listed_catalog if isinstance(one, dict) and one.get("id")
    ][:3]
    #: 대표값이면서 수치인 물성 하나 — 채택 미리보기에 쓴다. 없는 물성으로 부르면
    #: 「담을 값이 없습니다」 만 보고 정작 담는 일이 되는지는 못 본다.
    adoptable: str | None = None
    adoptable_unit: str | None = None
    if catalog_id:
        detail = await call(
            session, "get_catalog_material", {"catalog_material_id": catalog_id}
        )
        # 덱이 지을 합성 곡선 — 못 지으면 `ok: false` 와 까닭이 맞는 답이다.
        await call(session, "preview_synthetic_curve", {"catalog_material_id": catalog_id})
        for one in detail.get("values") or [] if isinstance(detail, dict) else []:
            if (
                one.get("property_key")
                and isinstance(one.get("value"), int | float)
                and one.get("representative")
            ):
                adoptable = one["property_key"]
                adoptable_unit = one.get("unit")
                break
    # **곡선 · 산점의 점은 상세에 없다**(ADR 0072) — 벌 하나를 따로 받는다. 적층 재료에 S-N 이 있다.
    with_series = await call(session, "search_catalog", {"query": "L-PBF", "limit": 3})
    for one in (with_series.get("materials") or []) if isinstance(with_series, dict) else []:
        shown = await call(session, "get_catalog_material", {"catalog_material_id": one["id"]})
        series = (shown.get("series") or []) if isinstance(shown, dict) else []
        if series:
            await call(session, "get_catalog_series", {"series_id": series[0]["id"]})
            break
    # **반입 묶음 · 곡선 벌**(ADR 0067 · 0068) — 수집기가 쓰는 길. 미리보기 · 거절만 한다.
    #   한 번도 안 불리던 넷이다(2026-10-25). 조건 칸 경고(`warnings`)가 오는지도 이 자리에서 본다.
    batches = await call(session, "get_catalog_batch", {})
    listed = (batches.get("batches") or []) if isinstance(batches, dict) else []
    if isinstance(listed, list) and listed and isinstance(listed[0], dict):
        await call(session, "get_catalog_batch", {"key": listed[0]["key"]})
    if catalog_id:
        await call(
            session,
            "add_catalog_series",
            {
                "catalog_material_id": catalog_id,
                "kind": "curve",
                "label": "점검용 온도별 탄성계수",
                "quality_tier": 3,
                "source_kind": "journal",
                "source_title": "MCP 점검 — 저장하지 않는다",
                "method": "digitized",
                "x_key": "temperature_k",
                "x_unit": "°C",
                "columns": [{"property_key": "mechanical.youngs_modulus", "unit": "GPa"}],
                "rows": [[25, 200], [100, 195]],
                "conditions": {"aging_weeks": 1},
                "dry_run": True,
            },
        )
    await call(
        session, "delete_catalog_series", {"series_id": str(uuid.uuid4())}, expect_error=True
    )
    bundle = Path(os.environ.get("TEMP", ".")) / "matnexus_probe_bundle.json"
    bundle.write_text(
        json.dumps(
            {
                "batch": {"key": "probe/mcp-check", "title": "MCP 점검 — 저장하지 않는다"},
                "sources": [
                    {"key": "s", "kind": "journal", "title": "점검 문헌", "license": "CC-BY-4.0"}
                ],
                "materials": [{"key": "m", "name": "점검용 문헌 재료", "category": "metal"}],
                "values": [
                    {
                        "key": "v",
                        "material": "m",
                        "source": "s",
                        "property_key": "mechanical.youngs_modulus",
                        "value_num": 200,
                        "unit": "GPa",
                        "conditions": {"temperature_k": 296.15},
                        "method": "measured",
                        "quality_tier": 2,
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    try:
        await call(session, "import_catalog_batch", {"path": str(bundle), "dry_run": True})
    finally:
        bundle.unlink(missing_ok=True)
    if len(catalog_ids) >= 2:
        await call(session, "compare_catalog_materials", {"catalog_material_ids": catalog_ids})
    await call(session, "match_bom", {"text": "브래킷\tSPCC\n볼트\tSCM435"})

    # **도메인이 빠진 키는 일부러 넣는다** — 안내가 나오는지 보는 자리다.
    await call(session, "how_to_measure", {"property_key": "yield_strength"}, expect_error=True)
    await call(session, "how_to_measure", {"property_key": "mechanical.yield_strength"})

    # **시험 기반 카드 길**: 적합을 견주고, 초안을 미리보기까지 해 본다.
    #   DP600 은 시편 8개가 붙어 있어 대표 곡선이 나온다(개발 DB).
    fit_material = os.environ.get("MATNEXUS_PROBE_FIT_MATERIAL")
    if fit_material:
        await call(
            session,
            "preview_card_fit",
            {"material_id": fit_material, "test_type": "tensile", "orientation": "MD"},
        )
        # 대표 곡선 기준(ADR 0041) — 하한 · 평균 − 2σ.
        await call(
            session,
            "preview_card_fit",
            {
                "material_id": fit_material,
                "test_type": "tensile",
                "orientation": "MD",
                "basis": "lower",
                "basis_method": "sd",
                "basis_k": 2,
            },
        )
        await call(
            session,
            "create_card_from_tests",
            {
                "material_id": fit_material,
                "test_type": "tensile",
                "orientation": "MD",
                "label": "점검용 초안",
                "dry_run": True,
            },
        )

    runs = await call(session, "list_test_runs", {"limit": 30})
    # **채택 결과가 있는 시험**을 고른다 — 식 미리보기와 처리 입력이 그것을 받는다.
    # 첫 줄을 집으면 채택 없는 시험이 걸려 뒤의 도구들이 조용히 건너뛴다(2026-09-19).
    listed = (runs or {}).get("runs", []) if isinstance(runs, dict) else []
    run_id = next((one["id"] for one in listed if one.get("adopted")), None) or _first(
        runs, "id", "test_run_id"
    )
    if run_id:
        detail = await call(session, "get_test_run", {"test_run_id": run_id})
        # 다시 읽기(2026-10-20) — 미리보기만. 없는 형식은 서버에 닿기 전에 거절해야 한다.
        await call(session, "reparse_test_run", {"test_run_id": run_id, "dry_run": True})
        await call(
            session,
            "reparse_test_run",
            {"test_run_id": run_id, "profile_key": "없는-형식-점검", "dry_run": True},
            expect_error=True,
        )
        await call(session, "list_processing_inputs", {"test_run_id": run_id})
        # ── 처리 결과 — 채택 화면과 같은 목록, 그리고 결과 하나의 곡선(앞쪽 곡선 · E 선) ───
        listed_results = await call(session, "list_processing_results", {"test_run_id": run_id})
        rows_ = (listed_results or {}).get("results", []) if isinstance(listed_results, dict) else []
        pick = next((one for one in rows_ if one.get("adopted")), rows_[0] if rows_ else None)
        if pick:
            await call(session, "get_result_curve", {"result_id": pick["id"], "max_points": 40})
        # ── 계산식 — 읽고, 어휘를 보고, 채택 결과 하나에 **저장 없이** 돌려 본다 ───
        await call(session, "list_formulas")
        await call(session, "formula_vocabulary")
        adopted = (detail or {}).get("adopted_result_id") if isinstance(detail, dict) else None
        measured = (detail or {}).get("measured_values_si") if isinstance(detail, dict) else None
        if adopted and measured:
            first = measured[0]["key"]
            await call(
                session,
                "preview_formula",
                {
                    "spec": {
                        "key": "probe_only",
                        "kind": "scalar_step",
                        "label": "점검용 — 값 그대로",
                        "expression": f"{first} * 1",
                        "variables": [{"name": first, "unit": measured[0].get("unit") or "1"}],
                        "result": {
                            "key": "probe_only",
                            "label": "점검용",
                            "si_unit": measured[0].get("unit") or "1",
                        },
                    },
                    "result_id": adopted,
                },
            )
        # 시험이 든 시편으로 바로 들어간다 — 시편에는 제 목록이 따로 있지만,
        # **시험에서 시편으로 가는 길**이 실제로 쓰이는 길이다.
        specimen = (detail or {}).get("specimen") if isinstance(detail, dict) else None
        if isinstance(specimen, dict) and specimen.get("id"):
            await call(session, "get_specimen", {"specimen_id": specimen["id"]})
    # ── 점탄성 — 마스터커브가 있는 시험에서만 뜻이 있다 ────────────────────
    dma = next((one["id"] for one in listed if (one.get("master_curve_count") or 0) > 0), None)
    if dma:
        curves = await call(session, "get_master_curves", {"test_run_id": dma})
        found = (curves or {}).get("master_curves") if isinstance(curves, dict) else None
        sweeps = (curves or {}).get("sweeps") if isinstance(curves, dict) else None
        if sweeps:
            # 온도별 저장 탄성률 카드 — 미리보기는 표를 만들지 않는다(없으면 「넣을 때 만든다」).
            await call(
                session,
                "create_dma_temperature_card",
                {"test_run_ids": [dma], "label": "점검용", "dry_run": True},
            )
            await call(
                session,
                "build_master_curve",
                {
                    "test_run_id": dma,
                    "reference_temperature_k": sweeps[0]["temperature_k"],
                    "dry_run": True,
                },
            )
        if found:
            await call(
                session, "fit_prony", {"master_curve_id": found[0]["id"], "dry_run": True}
            )
            fits = await call(session, "get_prony_fits", {"master_curve_id": found[0]["id"]})
            listed_fits = (fits or {}).get("fits") if isinstance(fits, dict) else None
            if listed_fits:
                await call(
                    session,
                    "create_viscoelastic_card",
                    {"prony_fit_id": listed_fits[0]["id"], "label": "점검용", "dry_run": True},
                )
    await call(
        session,
        "create_card_from_group",
        {
            "group_result_id": "00000000-0000-0000-0000-000000000000",
            "label": "점검용",
            "plugin_id": "tensile.rate_family",
            "dry_run": True,
        },
    )
    if material_id:
        await call(
            session,
            "create_lve_card",
            {
                "material_id": material_id,
                "test_type": "dma_sweep",
                "orientation": "NA",
                "label": "점검용",
                "dry_run": True,
            },
        )
    recipes = await call(session, "list_recipes")
    rows = recipes.get("recipes") if isinstance(recipes, dict) else recipes
    recipe_key = rows[0].get("key") if isinstance(rows, list) and rows else None
    # 이름 고치기는 **미리보기로만** — 고칠 수 있는 레시피를 고른다(못 고치면 막히는 게 맞다).
    editable = next(
        (
            one
            for one in (rows if isinstance(rows, list) else [])
            if (one.get("access") or {}).get("can_edit") is not False
        ),
        None,
    )
    if editable:
        await call(
            session,
            "update_recipe",
            {"key": editable["key"], "label": f"{editable.get('label')} (점검)", "dry_run": True},
        )
    inbox = await call(session, "list_inbox", {"limit": 3})
    item_id = _first(inbox, "id", "item_id")

    await call(session, "inspect_device_file", {"sample_text": SAMPLE, "header_rows": 2})
    await call(
        session,
        "check_format_profile",
        {
            "sample_text": SAMPLE,
            "definition": DEFINITION,
            "header_rows": 2,
            "test_type": "tensile",
        },
    )
    await call(
        session,
        "draft_test_type",
        {
            "key": "probe_only",
            "label": "점검용",
            "channels": [{"key": "force", "si_unit": "N"}],
        },
    )
    await call(session, "scan_deck_format", {"deck_text": "*MAT_024\n$#     mid        ro\n"})
    # **해석용 정의를 짓는 길**(2026-09-30) — 문법 · 목록 · 카드에 그려 보기 · 저장(미리보기만).
    await call(session, "export_definition_grammar")
    await call(session, "list_export_profiles")
    if card_id:
        drafted = await call(
            session,
            "scan_deck_format",
            {"deck_text": "*MAT_ELASTIC\n         1   7.85E-9  210000.0       0.3\n", "card_id": card_id},
        )
        definition = (
            drafted.get("definition") if isinstance(drafted, dict) else None
        ) or {"lines": [{"text": "*KEYWORD"}]}
        # **초안의 빈 칸은 채울 자리다** — 사람(AI)이 하는 일을 흉내 내 탄성계수로 채운다.
        # 안 채우고 그리면 「값이 비어 있는 칸」 으로 거절되는 것이 맞다.
        for line in definition.get("lines") or []:
            for cell in line.get("fields") or []:
                if isinstance(cell, dict) and cell.get("value") == "":
                    cell["value"] = "elastic.youngs_modulus"
        await call(
            session,
            "preview_export_profile",
            {"definition": definition, "card_id": card_id, "extension": "k"},
        )
        await call(
            session,
            "save_export_profile",
            {"label": "점검용", "definition": definition, "extension": "k", "dry_run": True},
        )
    # **사내 물성 들이기**(2026-09-30) — 다섯 다 미리보기만.
    items = await call(session, "list_property_items")
    await call(
        session,
        "add_catalog_property",
        {"name": "점검용 물성", "domain": "mechanical", "slug": "probe_only", "si_unit": "1"},
    )
    await call(
        session,
        "add_property_item",
        {"name": "점검용 물성", "dimension": "dimensionless", "dry_run": True},
    )
    first_item = None
    if isinstance(items, dict):
        listed_items = items.get("items") or []
        first_item = listed_items[0].get("item") if listed_items else None
    if first_item:
        await call(
            session,
            "link_property_item",
            {"item": first_item, "property_key": "mechanical.youngs_modulus", "dry_run": True},
        )
    await call(
        session,
        "save_card_block",
        {
            "key": "probe_block",
            "label": "점검용",
            "produces": [{"key": "probe", "label": "점검", "si_unit": "1"}],
            "dry_run": True,
        },
    )
    if material_id and first_item:
        await call(
            session,
            "set_declared_values",
            {
                "material_id": material_id,
                "values": [
                    {"item": first_item, "value": 1.0, "source": "estimate", "reference": "점검"}
                ],
                "dry_run": True,
            },
        )

    await call(session, "get_ontology")
    if material_id:
        await call(session, "related", {"kind": "material", "id": material_id})
        if run_id:
            await call(
                session,
                "find_path",
                {
                    "from_kind": "material",
                    "from_id": material_id,
                    "to_kind": "test_run",
                    "to_id": run_id,
                },
            )
    # ── 측정 의뢰 — 짓는 것까지 **미리보기로** ───────────────────────────────
    commission_detail: Any = None
    commissions = await call(session, "list_commissions", {"limit": 3})
    listed = commissions.get("items") if isinstance(commissions, dict) else None
    commission = listed[0] if isinstance(listed, list) and listed else None
    if commission:
        commission_detail = await call(
            session, "get_commission", {"commission_id": commission["id"]}
        )
        lab = (commission.get("lab_workspace") or {}).get("slug")
        if lab:
            await call(
                session,
                "create_commission",
                {
                    "title": "점검용 의뢰",
                    "purpose": "MCP 점검 — 저장하지 않는다",
                    "lab": lab,
                    "material_hint": "점검용 새 재료(아직 등록 전)",
                    "items": [{"property_hint": "고온 탄성계수", "count": 1}],
                    "dry_run": True,
                },
            )
            # 받는 부서를 비우면 거절하고 TestScope 추천(`lab_suggestions`)을 준다(ADR 0069 C).
            await call(
                session,
                "create_commission",
                {
                    "title": "점검용 의뢰",
                    "purpose": "MCP 점검 — 저장하지 않는다",
                    "material_hint": "점검용 새 재료(아직 등록 전)",
                    "items": [{"test_type_key": "tensile", "count": 1}],
                    "dry_run": True,
                },
                expect_error=True,
            )

    sections = await call(
        session, "search_all", {"q": "단위", "kind": "guide_section", "limit": 2}
    )
    section_id = _first(sections, "id")
    if section_id:
        await call(session, "get_handbook_section", {"section_id": section_id})

    # ── 쓰기 — 전부 미리보기 ────────────────────────────────────────────────
    parameterized = os.environ.get("MATNEXUS_PROBE_PARAM_MATERIAL")
    if parameterized:
        await call(
            session, "get_catalog_parameter_sets", {"catalog_material_id": parameterized}
        )
        if material_id:
            await call(
                session,
                "adopt_parameter_set",
                {
                    "material_id": material_id,
                    "catalog_material_id": parameterized,
                    "property_key": os.environ.get(
                        "MATNEXUS_PROBE_PARAM_KEY", "mechanical.prony_relaxation_time"
                    ),
                    "dry_run": True,
                },
            )
    elif catalog_id:
        await call(session, "get_catalog_parameter_sets", {"catalog_material_id": catalog_id})

    if material_id and catalog_id and adoptable:
        await call(
            session,
            "adopt_catalog_values",
            {
                "material_id": material_id,
                "catalog_material_id": catalog_id,
                "property_keys": [adoptable],
                "dry_run": True,
            },
        )
    if material_id:
        await call(
            session,
            "create_declared_card",
            {"material_id": material_id, "label": "점검용 초안", "dry_run": True},
        )
    if run_id:
        one: dict[str, Any] = {"test_run_id": run_id}
        if recipe_key:
            one["recipe_key"] = recipe_key
        await call(session, "run_processing", one)
        batch: dict[str, Any] = {"test_run_ids": [run_id], "dry_run": True}
        if recipe_key:
            batch["recipe_key"] = recipe_key
        else:
            batch["steps"] = [{"kind": "trim"}]
        await call(session, "run_batch_processing", batch)
    await call(
        session,
        "save_recipe",
        {
            "label": "점검용",
            "test_type": "tensile",
            "steps": [{"kind": "trim"}],
            "dry_run": True,
        },
    )
    await call(
        session,
        "save_format_profile",
        {
            "key": "probe_only",
            "label": "점검용",
            "test_type": "tensile",
            "definition": DEFINITION,
            "dry_run": True,
        },
    )
    if item_id:
        await call(
            session,
            "assign_inbox_item",
            {
                "item_id": item_id,
                "specimen_id": "00000000-0000-0000-0000-000000000000",
                "test_type": "tensile",
                "dry_run": True,
            },
        )
    # ── 문헌 카탈로그에 넣기 — **아무것도 안 바꾸게**(2026-09-25) ───────────────
    # 값은 미리보기가 기본이다. 정의·재료는 미리보기가 없어 카탈로그에 없는 분류값으로
    # 부른다 — 서버가 쓰기 전에 422 로 거절한다(관리자 아닌 토큰이면 403, 어느 쪽이든
    # 아무것도 안 생긴다). 지우기·폐기·이관은 없는 id·키로.
    if catalog_id and adoptable and adoptable_unit:
        await call(
            session,
            "add_catalog_value",
            {
                "catalog_material_id": catalog_id,
                "property_key": adoptable,
                "value": 1.0,
                "unit": adoptable_unit,
                "quality_tier": 2,
                # 출처 종류다 — `handbook` 은 측정 방법(`method`)의 낱말이라 서버가 거절했다
                # (2026-10-20 프로브: 「출처 종류 'handbook' 는 없습니다」).
                "source_kind": "book",
                "source_title": "점검용 — 저장하지 않는다",
                "dry_run": True,
            },
        )
    await call(
        session,
        "add_catalog_material",
        {"name": "점검용 문헌 재료", "category": "__probe__"},
        expect_error=True,
    )
    await call(
        session,
        "add_catalog_property",
        {
            "name": "점검용 물성",
            "domain": "__probe__",
            "slug": "probe_only",
            "si_unit": "Pa",
            # 미리보기가 기본이 됐다(2026-09-30) — 서버까지 가서 거절당하는지 보려고 끈다.
            "dry_run": False,
        },
        expect_error=True,
    )
    await call(
        session,
        "delete_catalog_value",
        {"value_id": "00000000-0000-0000-0000-000000000000"},
        expect_error=True,
    )
    await call(
        session,
        "deprecate_catalog_property",
        {"property_key": "local.probe.nothing"},
        expect_error=True,
    )
    await call(
        session,
        "migrate_catalog_property",
        {"property_key": "local.probe.nothing"},
        expect_error=True,
    )
    if not item_id:
        # 수신함이 비었으면 **없는 항목으로** 부른다 — 도구가 서버까지 가는지는 본다.
        await call(
            session,
            "assign_inbox_item",
            {
                "item_id": "00000000-0000-0000-0000-000000000000",
                "specimen_id": "00000000-0000-0000-0000-000000000000",
                "test_type": "tensile",
                "dry_run": True,
            },
            expect_error=True,
        )
    if catalog_id:
        await call(
            session,
            "build_deck",
            {
                "rows": [{"mid": 1, "name": "점검용 부품", "catalog_material_id": catalog_id}],
                "include_text": True,
            },
        )

    # ── 2026-10-14 에 연 쓰기(ADR 0061) — 전부 미리보기, 상태가 안 맞으면 거절을 본다 ──
    zero = "00000000-0000-0000-0000-000000000000"
    if card_id:
        card = await call(session, "get_card", {"card_id": card_id})
        status = card.get("status") if isinstance(card, dict) else None
        action = {"draft": "publish", "published": "deprecate", "deprecated": "restore"}.get(
            str(status), "publish"
        )
        await call(
            session, "set_card_status", {"card_id": card_id, "action": action, "dry_run": True}
        )
        # 2026-10-16 — 코멘트 · 부탁. 초안이 아니면 확정 요청은 거절이 맞는 답이다.
        await call(
            session,
            "add_card_remark",
            {"card_id": card_id, "comment": "점검용 코멘트", "dry_run": True},
        )
        await call(
            session,
            "request_review",
            {"card_id": card_id, "dry_run": True},
            expect_error=status != "draft",
        )
    if material_id:
        await call(session, "request_review", {"material_id": material_id, "dry_run": True})
    if run_id:
        tried = await call(session, "list_processing_results", {"test_run_id": run_id})
        result_id = _first(tried, "id")
        await call(
            session,
            "adopt_results",
            {"items": [{"test_run_id": run_id, "result_id": result_id}], "dry_run": True},
        )
    if isinstance(commission_detail, dict) and commission_detail.get("id"):
        cid = commission_detail["id"]
        await call(
            session,
            "change_commission_status",
            {"commission_id": cid, "note": "MCP 점검 — 저장하지 않는다", "dry_run": True},
        )
        await call(
            session,
            "assign_commission",
            {"commission_id": cid, "assignee": None, "dry_run": True},
            expect_error=not commission_detail.get("can_assign"),
        )
        items = commission_detail.get("items") or []
        await call(
            session,
            "link_commission_run",
            {
                "commission_id": cid,
                "item_id": (items[0]["id"] if items else zero),
                "test_run_id": run_id or zero,
                "dry_run": True,
            },
            expect_error=not (commission_detail.get("can_link") and items and run_id),
        )
    # ── 2026-10-15 — 표로 시험 입력 · 검증 키트 ────────────────────────────────
    sample = await call(session, "list_samples", {"material_id": material_id}) if material_id else None
    # `_first` 는 `samples` 칸을 안 뒤진다 — 여기서만 직접 꺼낸다(2026-10-15 프로브에서 빠졌다).
    samples = (sample or {}).get("samples") if isinstance(sample, dict) else None
    sample_id = samples[0].get("id") if samples else None
    if sample_id:
        await call(
            session,
            "import_test_summaries",
            {
                "sample_id": sample_id,
                "test_type": "tensile",
                "columns": ["시편", "항복강도 (MPa)"],
                "rows": [["점검-없는-시편", 300]],
                "dry_run": True,
            },
        )
    tensile = await call(session, "list_cards", {"limit": 50})
    kit_card = next(
        (
            one
            for one in ((tensile or {}).get("cards") or [] if isinstance(tensile, dict) else [])
            if one.get("test_type") == "tensile" and "abaqus" in (one.get("available_formats") or [])
        ),
        None,
    )
    if kit_card:
        await call(session, "get_verify_kit", {"card_id": kit_card["id"], "format": "abaqus"})
    elif card_id:
        # 인장 카드가 없으면 키트가 없다는 거절이 맞는 답이다 — 서버까지 가는지만 본다.
        await call(
            session, "get_verify_kit", {"card_id": card_id, "format": "abaqus"}, expect_error=True
        )
    if specimen_id:
        await call(
            session,
            "upload_test_run",
            {
                "specimen_id": specimen_id,
                "test_type": "tensile",
                "filename": "probe.csv",
                "content": "displacement,force\n0,0\n0.1,100\n",
                "dry_run": True,
            },
        )
    await call(
        session,
        "create_vocabulary_term",
        {"vocabulary": "manufacturer", "value": "MCP 점검용 제조사", "dry_run": True},
    )
    await call(
        session,
        "add_vocabulary_alias",
        {"vocabulary": "manufacturer", "value": "없는 값 — 점검", "alias": "x", "dry_run": True},
        expect_error=True,
    )
    await call(
        session,
        "save_test_type",
        {
            "key": "probe_only",
            "label": "점검용 시험법",
            "abbr": "PRB",
            "channels": [
                {"key": "force", "label": "하중", "dimension": "force", "si_unit": "N"}
            ],
            "dry_run": True,
        },
    )
    profiles = await call(session, "list_export_profiles")
    rows = profiles.get("profiles") if isinstance(profiles, dict) else None
    if isinstance(rows, list) and rows:
        await call(
            session,
            "set_export_profile_active",
            {"key": rows[0]["key"], "is_active": not rows[0].get("is_active"), "dry_run": True},
        )

    missed = sorted(set(names) - {one["tool"] for one in results})
    print("\n부르지 못한 도구: " + (", ".join(missed) or "없음"))


async def main() -> int:
    token = os.environ.get("MATNEXUS_PAT")
    if not token:
        print("MATNEXUS_PAT 이 없습니다 — 화면의 「내 계정 → 토큰」 에서 발급하세요.")
        return 2

    env = dict(os.environ)
    env["MATNEXUS_API_BASE"] = API_BASE
    env["MATNEXUS_MCP_PORT"] = str(PORT)
    env["MATNEXUS_MCP_HOST"] = "127.0.0.1"
    env["PYTHONIOENCODING"] = "utf-8"
    # **서버 출력은 파일로 받는다.** PIPE 로 잡아 두고 안 읽으면 버퍼가 찬 순간
    # 서버가 write 에서 멈춘다 — 그러면 「그 도구가 서버를 죽였다」 처럼 보인다.
    log = (HERE / "probe-server.log").open("w", encoding="utf-8")
    server = subprocess.Popen(
        [sys.executable, "server.py"],
        cwd=str(HERE),
        env=env,
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    try:
        for _ in range(60):
            with socket.socket() as sock:
                sock.settimeout(0.3)
                if sock.connect_ex(("127.0.0.1", PORT)) == 0:
                    break
            if server.poll() is not None:
                print("서버가 떴다가 죽었다 — probe-server.log 를 보라")
                return 1
            time.sleep(0.5)
        else:
            print("서버가 안 떴다")
            return 1

        # **SDK 가 주는 클라이언트를 쓴다.** 손으로 `Timeout(60)` 을 주면 SSE 수신
        # 스트림까지 60초에 끊겨 첫 호출부터 ReadTimeout 이 난다(실측).
        http = create_mcp_http_client(headers={"Authorization": f"Bearer {token}"})
        async with (
            http,
            streamable_http_client(
                f"http://127.0.0.1:{PORT}/mcp", http_client=http
            ) as streams,
            ClientSession(streams[0], streams[1]) as session,
        ):
            await session.initialize()
            await sweep(session)
    finally:
        log.close()
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()

    bad = [one for one in results if not one["ok"]]
    print(
        f"\n=== 호출 {len(results)}건 · 성공 {len(results) - len(bad)} · 문제 {len(bad)} ==="
    )
    for one in bad:
        print(f"  [{one['tool']}] {one['excerpt'][:180]}")
    print(
        "\n오류라고 다 결함은 아니다 — 없는 물성으로 채택을 시도하면 「담을 값이"
        " 없습니다」 가 맞는 답이다. 무엇을 물었는지와 함께 읽어라."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
