"""장비 파일의 **구조**를 읽는다. 의미는 모른다.

이 패키지가 있는 이유가 이 프로젝트의 확장성 전부다.

장비 종류가 늘 때마다 파서를 짜면 두 가지가 막힌다. 하나는 개발 비용이고, 다른
하나가 더 크다 — **현장에 있는 파일이 개발자에게 오지 않는다.** 폐쇄망이면 더
그렇다. 파일을 받아야 파서를 만들 수 있고, 만들면 배포해야 하고, 그 왕복 동안
데이터는 안 들어온다.

실측해 보니 장비 파일들은 구조가 놀랄 만큼 비슷하다. Zwick 인장기와 TA DMA850 은
만든 회사도 측정하는 물리량도 다른데, 파일은 둘 다 이 모양이다.

    키,값                    ← 메타 블록
    ...
    [마커]                   ← 있을 수도 없을 수도
    표 이름                  ← 있을 수도 없을 수도
    채널,채널,채널            ← 헤더
    단위,단위,단위            ← 있을 수도 없을 수도
    숫자,숫자,숫자            ← 데이터
    ...                      ← 표가 반복될 수도

그래서 **구조는 코드가 한 번 읽고, 의미는 사람이 한 번 매핑한다.** 이 모듈은
앞쪽만 한다 — 여기서 나오는 것은 "3열짜리 표가 18행 있고 헤더는 이것" 까지이고,
그 열이 변위인지 하중인지는 모른다.

DB 도 HTTP 도 모른다. 바이트가 들어오고 구조가 나간다.
"""

from __future__ import annotations

from matcore.readers.json_tables import looks_like_json, read_json
from matcore.readers.tabular import (
    ReadError,
    ReadOptions,
    Table,
    TabularFile,
    read,
    sniff,
)

__all__ = [
    "ReadError",
    "ReadOptions",
    "Table",
    "TabularFile",
    "looks_like_json",
    "read",
    "read_json",
    "sniff",
]
