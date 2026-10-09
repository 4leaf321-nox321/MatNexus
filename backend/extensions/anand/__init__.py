"""Anand 점소성 — 솔더(SAC305 · SAC405 · 63Sn37Pb …)의 표준 모델을 덱으로(2026-10-08).

카드의 **모델 파라미터 블록**(`model_params`, ADR 0029)이 든 Anand 9항을 ANSYS 의
`TB,RATE,,,,ANAND` 로 낸다. 9항은 낱개로는 뜻이 없는 한 벌이라 카드는 벌을 인용만 하고
(재료가 원본을 든다), 문헌 덱은 카탈로그의 벌을 같은 블록으로 싣는다(`shared/litdeck`).

등록은 렌더러 하나다 — 계산은 `deck.py`.
"""

from __future__ import annotations

from . import deck  # noqa: F401  (import 만으로 렌더러를 등록한다)
