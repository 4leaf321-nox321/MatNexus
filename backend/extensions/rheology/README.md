# 유변 (점도)

레오미터 유동 시험의 점도-전단율 곡선에 Cross · Carreau 를 맞추고(`equations.py`), 그 계수를
카드 블록 `rheology` 에 담아 덱으로 낸다(`card.py`).

## 덱

| 형식 | 키워드 | 우리 식에서 옮기는 것 |
| --- | --- | --- |
| Abaqus (점도) | `*VISCOSITY, DEFINITION=CROSS \| CARREAU-YASUDA` | Cross 지수를 `n = 1 - m` 으로 돌린다 · Carreau 는 a = 2 |
| LS-DYNA (점도 · ICFD) | `*ICFD_MAT` + `*ICFD_MODEL_NONNEWT` | Cross 는 NNID=5(Cross II), **지수 m 그대로** · Carreau 는 NNID=2, ALPHA=0 |

**같은 Cross 인데 솔버마다 지수를 반대로 받는다.** Abaqus 는 `(λ·rate)^(1-n)`, LS-DYNA Cross II
는 `(λ·rate)^n` 이다. 한쪽 규약을 다른 쪽에 옮겨 오면 박화가 반대로 가는데 덱은 멀쩡히 돈다 —
시험(`test_ext_rheology.py`)이 두 자리를 따로 지킨다.

LS-DYNA ICFD 에서 조심할 것(R16 매뉴얼 Vol III, 2026-10-08 확인):

- **LAMBDA 의 기본이 1e30** 이다 — 비우면 첫 전단율부터 박화가 끝난 점도가 된다. 늘 적는다.
- NNID=3(Cross)은 무한 전단 점도 μ∞ 가 없어 쓰지 않는다 — Cross II 가 우리 식이다.
- `*ICFD_MAT` 둘째 카드(열)는 **빈 카드**다. 0 으로 채우면 PRT 기본 0.85 가 0 이 된다.
- 밀도가 없으면 내지 않는다 — RO 기본이 0 이다. VIS 에는 영전단 점도를 적는다(비뉴턴 모델이
  점도를 정하지만 뉴턴 점도 칸을 0 으로 두지 않는다).

## 낼 수 없는 솔버

OptiStruct · Nastran · OpenRadioss · ANSYS Mechanical 은 고체 재료에 전단 박화 점도를 받는 입력이
없다(매뉴얼 조사, 2026-10-08). ANSYS Fluent 는 Carreau(a=2)가 정확히 같고 Cross 는 μ∞ = 0 일
때만 같다 — 설정을 적는 길(TUI · 저널)이 확인되지 않아 만들지 않았다.
