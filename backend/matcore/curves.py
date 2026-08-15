"""곡선의 직렬화와 표시용 축약.

**왜 Parquet 인가.** 시험 하나가 수천~수만 행이고 채널이 여럿이다. 차트는 보통
그중 두 열만 쓴다. 행 지향 형식(CSV·JSON)은 두 열을 보려고 전부 읽어야 하지만,
Parquet 은 필요한 열만 읽는다. 타입과 열 이름이 파일에 들어 있어 "이 컬럼이 뭐였지"
를 별도 문서에 의존하지 않는 것도 크다. 대가는 배포 번들 28MB(pyarrow) 다.

**왜 축약이 여기 있는가.** 3만 점을 그대로 브라우저로 보내면 JSON 이 수 MB 가 되고
차트가 버벅인다. 그렇다고 일정 간격으로 솎으면 **뾰족한 곳이 사라진다** — 인장
곡선에서 항복점과 최대하중이 정확히 그 뾰족한 곳이다. LTTB 는 구간마다 면적이
가장 큰 점을 남겨 그 모양을 지킨다.

이 모듈은 DB 도 HTTP 도 파일시스템도 모른다. 바이트가 들어오고 바이트가 나간다.
"""

from __future__ import annotations

import io
from collections.abc import Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from matcore.parsers import Channel

#: 열 이름과 함께 저장하는 부가 정보. Parquet 스키마 메타데이터에 들어간다.
#: 파일만 있고 DB 가 없어도 단위를 알 수 있어야 한다 — 백업에서 곡선만 복구하는
#: 경우가 실제로 생긴다.
_UNIT_PREFIX = b"unit:"
_SOURCE_UNIT_PREFIX = b"source_unit:"
_LABEL_PREFIX = b"label:"


def to_parquet(channels: Sequence[Channel], *, compression: str = "zstd") -> bytes:
    """채널들을 Parquet 바이트로. 모든 채널의 길이가 같아야 한다."""
    if not channels:
        raise ValueError("채널이 없습니다.")
    lengths = {len(channel.values) for channel in channels}
    if len(lengths) != 1:
        raise ValueError(f"채널 길이가 서로 다릅니다: {sorted(lengths)}")

    arrays = [pa.array(channel.values, type=pa.float64()) for channel in channels]
    metadata: dict[bytes, bytes] = {}
    for channel in channels:
        key = channel.key.encode()
        metadata[_UNIT_PREFIX + key] = channel.si_unit.encode()
        metadata[_LABEL_PREFIX + key] = channel.label.encode()
        if channel.source_unit:
            metadata[_SOURCE_UNIT_PREFIX + key] = channel.source_unit.encode()

    schema = pa.schema(
        [pa.field(channel.key, pa.float64()) for channel in channels], metadata=metadata
    )
    sink = io.BytesIO()
    pq.write_table(pa.Table.from_arrays(arrays, schema=schema), sink, compression=compression)
    return sink.getvalue()


def read_columns(
    data: bytes, keys: Sequence[str] | None = None
) -> dict[str, list[float | None]]:
    """필요한 열만 읽는다. `keys` 가 없으면 전부.

    없는 열을 달라고 하면 조용히 빼지 않고 실패한다 — 차트가 빈 축을 그리는
    것보다 무엇이 없는지 알려 주는 편이 낫다.
    """
    table = pq.read_table(io.BytesIO(data), columns=list(keys) if keys else None)
    return {name: table.column(name).to_pylist() for name in table.column_names}


def column_names(data: bytes) -> list[str]:
    return list(pq.read_schema(io.BytesIO(data)).names)


def downsample(
    xs: Sequence[float | None], ys: Sequence[float | None], *, max_points: int
) -> list[tuple[float, float]]:
    """LTTB(Largest-Triangle-Three-Buckets). 모양을 지키면서 점 수를 줄인다.

    일정 간격 솎기와의 차이가 실질적이다. 항복점처럼 국소적으로 꺾이는 지점은
    간격 솎기에서 그냥 사라지는데, 그 점이 우리가 곡선을 보는 이유다.

    None(결측)은 먼저 버린다. 곡선 중간의 구멍을 이어 그리면 없는 데이터를
    있는 것처럼 보여 주게 된다 — 잇지 않고 뺀다.
    """
    points = [
        (float(x), float(y))
        for x, y in zip(xs, ys, strict=True)
        if x is not None and y is not None
    ]
    if max_points < 3 or len(points) <= max_points:
        return points

    # 첫 점과 끝 점은 항상 남긴다. 곡선의 시작과 끝은 사람이 반드시 본다.
    bucket = (len(points) - 2) / (max_points - 2)
    result = [points[0]]
    previous = points[0]

    for index in range(max_points - 2):
        start = int((index + 1) * bucket) + 1
        end = min(int((index + 2) * bucket) + 1, len(points) - 1)
        if start >= end:
            # 빈 버킷이다. 점 수가 max_points 에 가까우면 끝쪽에서 생긴다.
            # 여기서 직전 점을 대신 넣으면 **같은 점이 두 번** 들어가, 결과 개수는
            # 맞는데 실제 점은 하나 적은 상태가 된다. 건너뛰고 개수를 정직하게 준다.
            continue

        window = points[end : min(int((index + 3) * bucket) + 1, len(points))] or [points[-1]]
        avg_x = sum(p[0] for p in window) / len(window)
        avg_y = sum(p[1] for p in window) / len(window)

        best = max(
            points[start:end],
            key=lambda p: abs(
                (previous[0] - avg_x) * (p[1] - previous[1])
                - (previous[0] - p[0]) * (avg_y - previous[1])
            ),
        )
        result.append(best)
        previous = best

    result.append(points[-1])
    return result
