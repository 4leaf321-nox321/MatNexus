"""크리프 — 솔더의 정상상태 크리프(Garofalo)를 덱으로(2026-10-08).

카드의 **모델 파라미터 블록**(`model_params`, ADR 0029)에서 Garofalo 벌을 찾아 ANSYS 의 암시적
크리프(`TB,CREEP` TBOPT 8)로 낸다. Anand(확장 `anand`)와 함께 솔더 신뢰성 해석의 두 축이다 —
Anand 는 점소성 하나로, Garofalo 는 탄소성 위에 크리프를 얹는다.

크리프 · 응력완화 시험이 앱에 들어오면(새 시험 종류) 이 폴더가 그 적합도 맡는다.
"""

from __future__ import annotations

from . import deck  # noqa: F401  (import 만으로 렌더러를 등록한다)
