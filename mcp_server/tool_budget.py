"""도구 목록의 크기를 잰다 — **클라이언트가 대화마다 싣는 양** (2026-10-03).

    python tool_budget.py          큰 것부터 20개와 합계
    python tool_budget.py --all    전부

도구 설명은 매 요청 상주 비용이다([계획] MCP 서버 — 「도구가 늘면 토큰이 는다」). 클라이언트는
대화마다 도구 목록 전체를 싣고, 그만큼 AI 가 일에 쓸 자리가 준다. 실측(2026-10-03): 96개의
목록이 104,331자 — 설명 49,552 · 인자 스키마 36,794 · 반환 스키마 8,498.

서버를 띄우지 않는다 — 도구 목록은 서버 모듈이 들고 있다(`mcp.list_tools()`). 설명만이 아니라
인자 · 반환 스키마까지 잰다: 클라이언트에는 셋이 함께 간다.

**예산은 설명에만 건다**(`backend/tests/architecture/test_mcp_tools.py`). 설명은 사람이 쓰는
부분이고, 스키마는 인자 이름 · 형 · 기본값에서 저절로 나온다. 예산에 걸리면 설명을 줄이거나
(예시 · 배경은 `get_guide` 로), 안 쓰는 도구를 뺀다 — 부른 횟수는 `usage_report.py` 가 센다.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import server


async def measure() -> list[dict[str, Any]]:
    """도구마다 설명 · 인자 · 반환 · 전체(JSON) 글자 수. 큰 것부터."""
    rows: list[dict[str, Any]] = []
    for tool in await server.mcp.list_tools():
        dumped = tool.model_dump(mode="json", by_alias=True, exclude_none=True)
        output = dumped.get("outputSchema")
        rows.append(
            {
                "name": tool.name,
                "description": len(tool.description or ""),
                "input": len(json.dumps(dumped.get("inputSchema") or {}, ensure_ascii=False)),
                "output": len(json.dumps(output, ensure_ascii=False)) if output else 0,
                "total": len(json.dumps(dumped, ensure_ascii=False)),
            }
        )
    return sorted(rows, key=lambda row: -row["total"])


def main() -> None:
    parser = argparse.ArgumentParser(description="MCP 도구 목록의 크기를 잰다")
    parser.add_argument("--all", action="store_true", help="20개만이 아니라 전부")
    args = parser.parse_args()
    # 윈도우 콘솔은 CP949 라 도구 이름 옆의 한글 머리가 깨진다.
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    rows = asyncio.run(measure())
    shown = rows if args.all else rows[:20]
    print(f"{'도구':<30} {'설명':>7} {'인자':>7} {'반환':>7} {'전체':>7}")
    for row in shown:
        print(
            f"{row['name']:<32} {row['description']:>7,} {row['input']:>7,} "
            f"{row['output']:>7,} {row['total']:>7,}"
        )
    if len(shown) < len(rows):
        print(f"… 그 밖 {len(rows) - len(shown)}개 (--all 로 전부)")
    totals = {key: sum(row[key] for row in rows) for key in ("description", "input", "output")}
    whole = sum(row["total"] for row in rows)
    print(
        f"\n도구 {len(rows)}개 — 설명 {totals['description']:,} · 인자 {totals['input']:,} · "
        f"반환 {totals['output']:,} · 목록 전체 {whole:,}자"
    )


if __name__ == "__main__":
    main()
