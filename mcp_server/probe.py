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
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import subprocess
import sys
import time
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


async def call(session: ClientSession, name: str, args: dict[str, Any] | None = None) -> Any:
    """한 번 부르고 결과를 적는다. **오류도 200 으로 온다** — 본문을 봐야 안다."""
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
    bad = bool(out.is_error) or '"error"' in body[:400]
    results.append({"tool": name, "ok": not bad, "ms": took, "excerpt": body[:220]})
    print(("!! " if bad else "OK ") + f"{name}  {took}ms  " + " ".join(body[:130].split()))
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
    await call(
        session, "find_by_property", {"property": "yield_strength", "unit": "MPa", "min": 100}
    )

    if material_id:
        await call(session, "get_material", {"material_id": material_id})
        await call(session, "get_parameter_sets", {"material_id": material_id})
        await call(session, "get_statistics", {"material_id": material_id})
        await call(session, "compare_material_statistics", {"material_ids": [material_id]})
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
    await call(session, "list_specimens", {"limit": 2})
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
    if catalog_id:
        detail = await call(
            session, "get_catalog_material", {"catalog_material_id": catalog_id}
        )
        for one in detail.get("values") or [] if isinstance(detail, dict) else []:
            if (
                one.get("property_key")
                and isinstance(one.get("value"), int | float)
                and one.get("representative")
            ):
                adoptable = one["property_key"]
                break
    if len(catalog_ids) >= 2:
        await call(session, "compare_catalog_materials", {"catalog_material_ids": catalog_ids})
    await call(session, "match_bom", {"text": "브래킷\tSPCC\n볼트\tSCM435"})

    # **도메인이 빠진 키는 일부러 넣는다** — 안내가 나오는지 보는 자리다.
    await call(session, "how_to_measure", {"property_key": "yield_strength"})
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

    runs = await call(session, "list_test_runs", {"limit": 3})
    run_id = _first(runs, "id", "test_run_id")
    if run_id:
        detail = await call(session, "get_test_run", {"test_run_id": run_id})
        await call(session, "list_processing_inputs", {"test_run_id": run_id})
        # 시험이 든 시편으로 바로 들어간다 — 시편에는 제 목록이 따로 있지만,
        # **시험에서 시편으로 가는 길**이 실제로 쓰이는 길이다.
        specimen = (detail or {}).get("specimen") if isinstance(detail, dict) else None
        if isinstance(specimen, dict) and specimen.get("id"):
            await call(session, "get_specimen", {"specimen_id": specimen["id"]})
    recipes = await call(session, "list_recipes")
    rows = recipes.get("recipes") if isinstance(recipes, dict) else recipes
    recipe_key = rows[0].get("key") if isinstance(rows, list) and rows else None
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
    if catalog_id:
        await call(
            session,
            "build_deck",
            {
                "rows": [{"mid": 1, "name": "점검용 부품", "catalog_material_id": catalog_id}],
                "include_text": True,
            },
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
