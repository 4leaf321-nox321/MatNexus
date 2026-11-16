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

import hashlib
import io
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

from matcore.parsers import Channel

#: 열 이름과 함께 저장하는 부가 정보. Parquet 스키마 메타데이터에 들어간다.
#: 파일만 있고 DB 가 없어도 단위를 알 수 있어야 한다 — 백업에서 곡선만 복구하는
#: 경우가 실제로 생긴다.
_UNIT_PREFIX = b"unit:"
_SOURCE_UNIT_PREFIX = b"source_unit:"
_LABEL_PREFIX = b"label:"
#: 열과 **길이가 다른** 부가 정보(JSON 바이트) — 처리 결과의 「자르기 전 곡선」 이 그렇다.
#: 열로 넣으면 길이를 맞추려 빈 칸을 채워야 하고, 그러면 행 수가 거짓말을 한다.
_EXTRA_PREFIX = b"extra:"


def to_parquet(
    channels: Sequence[Channel],
    *,
    compression: str = "zstd",
    extra: Mapping[str, bytes] | None = None,
) -> bytes:
    """채널들을 Parquet 바이트로. 모든 채널의 길이가 같아야 한다.

    `extra` 는 스키마 메타데이터에 함께 싣는다(`read_extra` 로 읽는다) — 파일이 불변이라
    나중에 덧붙일 수 없는 것을 **처음부터** 같이 둔다.
    """
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
    for name, value in (extra or {}).items():
        metadata[_EXTRA_PREFIX + name.encode()] = value

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


def read_units(data: bytes) -> dict[str, str]:
    """열 이름 → SI 단위. **파일이 이미 알고 있다.**

    `to_parquet` 이 스키마 메타데이터에 심어 둔 값을 그대로 읽는다. 저장할 때는
    넣어 놓고 읽는 함수가 없어서, 저장된 결과를 그리려면 축 이름만 있고 단위는
    없는 상태였다 — 응력이 Pa 인지 MPa 인지 모르는 축은 읽을 수 없다.
    """
    schema = pq.read_schema(io.BytesIO(data))
    metadata = schema.metadata or {}
    return {
        key[len(_UNIT_PREFIX) :].decode(): value.decode()
        for key, value in metadata.items()
        if key.startswith(_UNIT_PREFIX)
    }


def read_extra(data: bytes, name: str) -> bytes | None:
    """`to_parquet(extra=…)` 로 실은 것. **없으면 None** — 그 칸이 생기기 전에 쓴 파일이다.

    「비어 있다」 와 「없다」 를 가른다: 쓴 쪽이 「해당 없음」 을 말하려면 값을 적는다.
    """
    schema = pq.read_schema(io.BytesIO(data))
    return (schema.metadata or {}).get(_EXTRA_PREFIX + name.encode())


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


#: 지문에 쓰는 유효숫자 — 장비 · 형식이 같은 값을 다른 자릿수로 적어도(1.2340 · 1.234) 같게
#: 본다.
FINGERPRINT_DIGITS = 10


def fingerprint(columns: Mapping[str, Sequence[float | None]]) -> str | None:
    """곡선의 **값 지문** — SI 값을 유효숫자 10자리로 반올림해 해시한다(2026-11-14, VOC 54).

    원본 파일의 SHA 는 줄끝 · 머리말 · 형식 · 단위만 달라도 달라진다. 곡선은 읽을 때 이미 SI 로
    바뀌어 저장되므로(Decimal 환산), SI 값의 지문은 **단위만 다른 사본**(N/kN · mm/m · %/비율)
    도 같게 본다. 못 잡는 것: 자릿수가 다르게 적힌 사본(1.235 kN 과 1234.56 N), 점을 솎거나
    자른 사본 — 그것은 근사 비교의 몫이다.

    열 이름 차례와 무관하다(이름순). 열이 없으면 `None`.
    """
    if not columns:
        return None
    digest = hashlib.sha256()
    for key in sorted(columns):
        digest.update(key.encode("utf-8") + b"\x00")
        for value in columns[key]:
            if value is None or value != value:  # NaN
                digest.update(b"n;")
            else:
                digest.update(format(float(value), f".{FINGERPRINT_DIGITS}g").encode() + b";")
        digest.update(b"\x01")
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 근사 사본 — 자릿수 · 점 간격 · 단위 배수만 다른 곡선(2026-11-17, VOC 54 · ADR 0091)
# ---------------------------------------------------------------------------

#: 모양에 남기는 점 수 — 축 열의 [최소, 최대] 를 고르게 나눈 자리.
SHAPE_POINTS = 64
#: 모양에 적는 유효숫자 — 견줄 차이(0.4 %)보다 훨씬 잘다. JSON 크기를 줄인다.
SHAPE_DIGITS = 7
#: 「거의 같다」 의 기준 — 채널 폭 대비 차이의 95 번째 백분위. **잠정값**(개발 DB 실측,
#: 2026-11-17): 같은 재료의 다른 시험끼리는 가장 가까운 쌍이 0.57 %(예제 파일을 늘려 만든
#: 데모)였고, 따로 잰 시편은 1.4 % 넘게 달랐다. 유효숫자 4자리로 줄인 사본은 최악 0.28 %,
#: 5 · 10점에 하나로 솎은 사본은 0.33 %, 단위 배수만 다른 사본은 0 이었다(원본 44개). 3자리로
#: 줄인 사본은 절반만 잡힌다.
NEAR_COPY = 0.004
#: 단위를 잘못 적었을 때 생기는 배율 — SI 로 바꾼 뒤에도 이 배수만큼 어긋난다.
UNIT_FACTORS: tuple[float, ...] = (
    1.0,
    9.80665,  # kgf · gf
    25.4,  # in
    6894.757,  # psi
    4.448222,  # lbf
    60.0,  # min
    3600.0,  # h
    *(10.0**power for power in range(-9, 10) if power),
)
#: 배율 · 축 범위를 견줄 때 남기는 여유 — 솎으면 양 끝 몇 점이 빠져 축 범위가 몇 % 준다.
_SHAPE_SLACK = 0.05
#: 폭이 크기의 이 비율 아래인 채널은 「거의 상수」 — 폭 대신 크기로 나눈다(시편 폭 열 등).
_SHAPE_FLAT = 1e-3


def _rises(values: np.ndarray) -> bool:
    kept = values[np.isfinite(values)]
    steps = np.diff(kept)
    return len(steps) > 5 and bool(kept[-1] > kept[0]) and float(np.mean(steps >= 0)) >= 0.98


def _rounded(values: np.ndarray) -> list[float]:
    return [float(f"{one:.{SHAPE_DIGITS}g}") for one in values]


def shape(columns: Mapping[str, Sequence[float | None]]) -> dict[str, object] | None:
    """곡선의 **작은 모양** — 늘기만 하는 열(축)을 고르게 나눈 64 자리에서 다른 열의 값.

    값 지문(`fingerprint`)은 정확히 같은 값만 알아본다. 자릿수를 줄여 저장한 사본 · 점을
    솎은 사본 · 단위를 잘못 적어 한 열이 일정한 배수로 어긋난 사본은 지문이 달라 통계에 두 번
    들어갔다. 모양은 축 위의 자리에서 재므로 솎아도 같고, 배율은 견줄 때(`near_copy`) 단위
    상수로 맞춘다.

    축은 이름순으로 처음 「늘기만 하는」 열(98 % 넘는 걸음이 0 이상)이다 — 인장은 변위, DMA
    변형률 스윕은 진동 변형률. 그런 열이 없으면 행 차례(0~1)로 잰다. 값이 10개 미만인 열은
    뺀다.
    """
    arrays: dict[str, np.ndarray] = {}
    for key, values in columns.items():
        row = np.array([np.nan if one is None else float(one) for one in values], dtype=float)
        if int(np.isfinite(row).sum()) >= 10:
            arrays[key] = row
    if not arrays:
        return None
    lead = next((key for key in sorted(arrays) if _rises(arrays[key])), None)
    if lead is None:
        at = np.linspace(0.0, 1.0, SHAPE_POINTS)
        grid: dict[str, list[float]] = {}
        for key, row in arrays.items():
            kept = row[np.isfinite(row)]
            grid[key] = _rounded(np.interp(at, np.linspace(0.0, 1.0, len(kept)), kept))
        return {"lead": None, "grid": grid}
    axis = arrays[lead]
    has_axis = np.isfinite(axis)
    # 축이 잡음으로 잠깐 내려가도 차례를 지킨다 — 보간은 오르는 축이 필요하다.
    running = np.maximum.accumulate(np.where(has_axis, axis, -np.inf))
    low, high = float(np.nanmin(axis)), float(np.nanmax(axis))
    spots = np.linspace(low, high, SHAPE_POINTS)
    grid = {}
    for key in sorted(arrays):
        row = arrays[key]
        # 축과 값을 **같은 행에서** 짝짓는다 — 빈 칸이 다른 자리에 있어도 어긋나지 않는다.
        both = has_axis & np.isfinite(row) if key != lead else np.zeros(len(row), dtype=bool)
        if int(both.sum()) >= 10:
            grid[key] = _rounded(np.interp(spots, running[both], row[both]))
    if not grid:
        return None
    return {"lead": lead, "low": low, "high": high, "grid": grid}


_FACTOR_ARRAY = np.asarray(UNIT_FACTORS)


@dataclass(frozen=True)
class Shape:
    """저장된 모양(`shape` 의 JSON)을 견주기 좋게 편 것 — 채널은 이름순, 채널마다 한 줄."""

    lead: str | None
    low: float
    high: float
    keys: tuple[str, ...]
    grid: np.ndarray

    @classmethod
    def of(cls, stored: Mapping[str, object] | None) -> Shape | None:
        """JSON 모양 → `Shape`. 모양이 아니면 `None`(옛 · 깨진 칸은 견주지 않는다)."""
        if not stored or not isinstance(stored.get("grid"), dict):
            return None
        grid = stored["grid"]
        assert isinstance(grid, dict)
        keys = tuple(sorted(grid))
        try:
            values = np.asarray([grid[key] for key in keys], dtype=float)
            low = float(stored.get("low") or 0.0)  # type: ignore[arg-type]
            high = float(stored.get("high") or 0.0)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        if values.ndim != 2 or values.shape[1] != SHAPE_POINTS or not keys:
            return None
        lead = stored.get("lead")
        return cls(lead if isinstance(lead, str) else None, low, high, keys, values)


def _unit_factor(ratio: float) -> float | None:
    if not ratio > 0 or ratio == float("inf"):
        return None
    best = min(UNIT_FACTORS, key=lambda one: abs(ratio / one - 1))
    return best if abs(ratio / best - 1) <= _SHAPE_SLACK else None


def near_copy(mine: Shape, other: Shape) -> tuple[float, dict[str, float]] | None:
    """`other` 가 `mine` 의 근사 사본인가 — `(차이, 채널마다 배율)`. 견줄 수 없으면 `None`.

    차이는 채널마다 「`other` 의 자리에서 본 `mine` 에 배율을 곱한 값과 `other` 의 차이」 를 그
    채널의 폭으로 나눈 값의 95 번째 백분위 중 가장 큰 것이다 — `NEAR_COPY` 아래면 거의 같다.
    배율은 단위 상수(`UNIT_FACTORS`) 중 가장 가까운 것이고, 5 % 넘게 어긋나면 견주지 않는다.
    축이 다르거나 채널 목록이 다르면 견주지 않는다. 방향이 있다(겹친 축 구간을 `other` 의
    자리로 잰다) — 두 방향 중 작은 쪽을 쓴다. 업로드마다 같은 재료의 곡선 수천 개와 견주므로
    채널을 한꺼번에 계산한다.
    """
    if mine.lead != other.lead or mine.keys != other.keys:
        return None
    factors: dict[str, float] = {}
    if mine.lead is None:
        a, b = mine.grid, other.grid
    else:
        if not mine.high > mine.low or not other.high > other.low:
            return None
        lead_factor = _unit_factor((other.high - other.low) / (mine.high - mine.low))
        if lead_factor is None:
            return None
        factors[mine.lead] = lead_factor
        low_a, high_a = mine.low * lead_factor, mine.high * lead_factor
        start, end = max(low_a, other.low), min(high_a, other.high)
        # 겹친 축 구간이 양쪽 다 90 % 는 돼야 한다 — 잘린 곡선은 이 판정의 몫이 아니다.
        if end - start < 0.9 * (high_a - low_a) or end - start < 0.9 * (
            other.high - other.low
        ):
            return None
        x_b = np.linspace(other.low, other.high, SHAPE_POINTS)
        inside = (x_b >= start) & (x_b <= end)
        # `mine` 의 자리는 고른 간격이라 보간 자리를 셈으로 낸다 — 모든 채널이 같은 자리를 쓴다
        # (`np.interp` 와 같은 값).
        place = (x_b[inside] - low_a) / (high_a - low_a) * (SHAPE_POINTS - 1)
        left = np.clip(np.floor(place).astype(int), 0, SHAPE_POINTS - 2)
        weight = np.clip(place - left, 0.0, 1.0)
        a = mine.grid[:, left] * (1 - weight) + mine.grid[:, left + 1] * weight
        b = other.grid[:, inside]
    # 배율은 단위 상수 중 가장 가까운 것만 고르면 되므로 절댓값 평균의 비로 충분하다.
    middle_a = np.mean(np.abs(a), axis=1)
    middle_b = np.mean(np.abs(b), axis=1)
    both_zero = (middle_a == 0) & (middle_b == 0)
    if np.any((middle_a == 0) & ~both_zero):
        return None
    ratio = np.where(both_zero, 1.0, middle_b / np.where(middle_a == 0, 1.0, middle_a))
    nearest = _FACTOR_ARRAY[
        np.argmin(np.abs(ratio[:, None] / _FACTOR_ARRAY[None, :] - 1), axis=1)
    ]
    if np.any(np.abs(ratio / nearest - 1) > _SHAPE_SLACK):
        return None
    size = np.max(np.abs(b), axis=1)
    span = np.max(b, axis=1) - np.min(b, axis=1)
    scale = np.where(span > _SHAPE_FLAT * size, span, np.where(size > 0, size, 1.0))
    # 95 번째 자리 — 정렬해 그 자리를 집는다(`np.percentile` 보다 몇 배 빠르고 판정은 같다).
    ordered = np.sort(np.abs(a * nearest[:, None] - b), axis=1)
    gaps = ordered[:, int(0.95 * (ordered.shape[1] - 1))] / scale
    for key, factor in zip(mine.keys, nearest, strict=True):
        factors[key] = float(factor)
    return float(np.max(gaps)), factors


def copy_gap(first: Shape, second: Shape) -> tuple[float, dict[str, float]] | None:
    """두 모양의 차이 — `near_copy` 의 두 방향 중 작은 쪽. 견줄 수 없으면 `None`.

    배율은 `second` 가 `first` 의 몇 배인가다(작은 쪽이 거꾸로 잰 방향이면 뒤집어 준다).
    """
    forward = near_copy(first, second)
    backward = near_copy(second, first)
    if backward is not None and (forward is None or backward[0] < forward[0]):
        return backward[0], {key: 1.0 / value for key, value in backward[1].items()}
    return forward
