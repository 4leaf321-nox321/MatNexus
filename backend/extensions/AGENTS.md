# 확장 폴더에서 일할 때

루트 [AGENTS.md](../../AGENTS.md) 를 먼저 읽는다. 여기 적은 것은 **이 폴더에만
더 세게 적용되는 것**이다.

## 이 폴더 밖은 고치지 않는다

`backend/extensions/<이름>/` 안에서 끝낸다. 중심 코드(`backend/matcore/`,
`backend/app/`, `frontend/`, `backend/migrations/`)는 **다른 사람이 같은 시간에
고치고 있다.**

중심에 무언가 필요하면 **고치지 말고 멈춘다.** 무엇이 왜 필요한지 적어 요청한다.
「스코프 안에서 바로잡는다」 예외는 자기 소유 경로 안에서만이다.

## 새 물성은 폴더 하나로 끝난다

끝나지 않으면 그것은 확장 설계가 잘못된 것이므로, 우회하지 말고 말한다.
부를 수 있는 등록 함수는 넷이다.

| | |
| --- | --- |
| `matcore.registry.register` | 처리 플러그인 |
| `matcore.cards.register_block` | 물성 카드 블록 |
| `matcore.export.register_renderer` | CAE 덱 |
| `matcore.fitting.register_family` | 적합식 |

`extensions/<이름>/__init__.py` 가 그 함수를 부르면 로더가 폴더를 훑어 읽는다 —
중심 코드에 이름을 적지 않는다([extensions.py](../matcore/extensions.py)).

## 하지 않는 것

- **마이그레이션을 쓰지 않는다.** `matcore` 와 `extensions` 는 DB 를 모른다.
  필요해지면 그 자체가 설계를 다시 볼 신호다 — 요청한다.
- **`frontend/package.json` 을 만지지 않는다.** 버전을 올리는 것이 곧 배포
  결정이고, 릴리스는 플랫폼 개발자가 한다.
- **`docs/개발계획.md` 에 적지 않는다.** 같은 자리에 서로 덧붙이면 매번 충돌한다.
  발견한 것은 `extensions/<이름>/README.md` 에 적는다.

## DB 도 HTTP 도 모른다

`sqlalchemy`·`fastapi`·`app.*` 를 import 하면 `tests/architecture` 가 막는다.
막히면 우회로를 찾지 말고 — 그 import 가 필요하다는 것 자체가 계산이 잘못된
자리에 있다는 뜻이다.

## 시험

계산은 `matcore` 만으로 시험할 수 있다. `tests/unit/test_ext_<이름>.py` 에 두고,
**운영과 같은 길로**(확장 로더를 거쳐) 읽어서 확인한다 — 직접 import 해서
시험하면 로더가 못 읽는 상태를 못 잡는다.
