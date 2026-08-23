# 물성 확장

**폴더 하나를 만들면 새 물성이 붙는다.** 중심 코드는 안 고친다.

```
extensions/
  creep_norton/
    __init__.py      ← 등록만 한다
    equations.py     ← 계산식
```

기동할 때 이 폴더를 훑어 `<이름>/__init__.py` 를 읽는다(`matcore/extensions.py`).
**하나가 잘못돼도 나머지는 산다** — 실패한 것은 로그에 남고 그 물성만 목록에서
빠진다.

## `__init__.py` 가 하는 일

등록 셋이다. 무엇을 등록하느냐는 물성에 따라 다르다.

```python
from matcore import cards, export, fitting
from matcore.registry import Produced

# ① 담을 자리 — 값의 이름·뜻·단위
cards.register_block(
    cards.BlockSpec(
        key="creep",
        label="크리프",
        help="정하중에서 시간에 따라 늘어나는 거동.",
        produces=(
            Produced(key="a", label="계수 A", si_unit="1/s"),
            Produced(key="n", label="응력 지수", si_unit="1"),
        ),
        rows=(Produced(key="name", label="파라미터"), Produced(key="value", label="값")),
    )
)

# ② 계산식 — 어느 축에 맞추고 어느 자리에 담기는지
fitting.register_family(
    fitting.Family(
        key="norton",
        label="Norton 크리프",
        parameter_names=("a", "n"),
        parameter_units=("1/s", "1"),
        evaluate=...,  # (파라미터, x) -> y
        guess=...,
        bounds=...,
        describe="...",
        x_column="stress_true",
        y_column="strain_rate",
        block="creep",
    )
)


# ③ 솔버 — 어느 블록을 먹고 어떻게 적히는지
@export.register_renderer(
    key="abaqus_creep",
    label="Abaqus (크리프)",
    extension="inp",
    describe="*CREEP, LAW=STRAIN",
    keywords=("*CREEP",),
    needs=(export.Need("creep", values=("a", "n")),),
)
def render(deck: export.Deck) -> export.Rendered: ...
```

셋 다 필요한 것은 아니다. 계산만 더하면 ②만, 새 솔버만 더하면 ③만 쓴다.

## 실제로 붙여 보고 배운 것 둘

`ghosh_hardening/` 이 첫 확장이다. 만들면서 걸린 자리가 둘 있었다.

**① 로더의 패키지 이름을 하드코딩하지 않는다.**

    from matnexus_ext.ghosh_hardening import equation   ← 이러지 않는다
    from . import equation                              ← 이렇게

확장이 자기가 어디에 얹히는지 알 필요가 없다. 절대 경로로 적으면 로더가 바뀌는
순간 전부 고쳐야 하고, 폴더 이름을 바꾸는 것도 못 하게 된다.

**② 시험은 확장 폴더 안에 두지 않는다.**

거기 두면 pytest 가 그 폴더를 `sys.path` 에 얹고 `<이름>.test_x` 로 읽는데, 그
순간 `__init__.py` 가 돌아 **등록이 한 번 더 일어난다.** 그다음 확장 로더가 같은
폴더를 읽으면 같은 key 가 둘이 된다.

    ValueError: 적합식 key 중복: ghosh

**레지스트리가 제 일을 한 것이다.** 시험은 `backend/tests/` 에 두고, 거기서
`extensions.load()` 로 **운영과 같은 길**로 읽어서 본다
(`tests/unit/test_ext_ghosh.py` 참조).

## 지키는 것

- **이름이 겹치면 거절된다.** 같은 key 가 둘이면 어느 쪽이 도는지 알 수 없다
- **단위는 SI 로 담는다.** 화면이 실무 단위로 바꿔 보여 준다
- **없는 값을 지어내지 않는다.** 모르면 비운 채로 두고, 그 솔버로는 못 낸다고 말한다
- **시험을 함께 둔다** — 다만 `backend/tests/` 에(위 ② 참조). 답을 아는 곡선에서
  계수가 되돌아오는지 검산하는 것이 이 저장소의 방식이다

## 배포

`deploy_package.zip` 이 `backend` 를 통째로 담으므로 이 폴더가 저절로 따라간다.
따로 설치할 것이 없다 — 폐쇄망을 고려해 `pip install` 이 아니라 폴더로 둔 이유다.
