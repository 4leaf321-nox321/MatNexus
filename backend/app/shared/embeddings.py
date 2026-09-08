"""임베딩 — **글을 숫자 1024개로.**

의미 검색이 「낱말이 하나도 안 겹쳐도 뜻이 가까우면 찾는다」 를 할 수 있는 것은
글과 질문을 같은 공간의 벡터로 바꾸기 때문이다. 그 변환을 하는 자리다.

## 백엔드 셋 — 없어도 검색은 돈다

    off       기본값. 의미 검색이 꺼진다
    mock      텍스트 해시 → 결정적 단위벡터. **뜻은 없다** — 배관만 시험한다
    ollama    사내 호스트(bge-m3). 진짜다

`off` 가 기본인 이유: 설치 안 한 곳에서 켜져 있으면 검색마다 11434 를 두드리다
타임아웃한다 — 느려진 이유를 아무도 모른다.

`mock` 은 ReportArchive 에서 그대로 가져왔다. 같은 글은 늘 같은 벡터가 되므로
**「넣은 것을 그대로 찾을 수 있나」 는 시험할 수 있고**, 「뜻이 비슷한 것을 찾나」 는
못 한다. CI 에 Ollama 를 두지 않는 값이 그것보다 크다.

## 차원이 안 맞으면 거절한다

모델을 바꾸면 차원이 바뀐다. 섞여 들어가면 거리 계산이 **조용히 엉뚱해진다** —
오류도 안 나고 순위만 이상해진다. 그래서 받은 벡터의 길이를 매번 본다.
"""

from __future__ import annotations

import hashlib
import logging
import struct

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

BACKENDS = ("off", "mock", "ollama")


class EmbeddingError(RuntimeError):
    """만들지 못했다. 부르는 쪽은 **의미 검색만 접고 나머지는 계속한다.**"""


def backend() -> str:
    chosen = (get_settings().embedding_backend or "off").lower()
    return chosen if chosen in BACKENDS else "off"


def enabled() -> bool:
    return backend() != "off"


def dimension() -> int:
    return get_settings().embedding_dim


def _mock_vector(text: str, dim: int) -> list[float]:
    """해시로 만든 결정적 단위벡터. 같은 글 → 같은 벡터.

    **뜻은 담기지 않는다.** 배관(청크→임베딩→저장→검색)이 도는지만 본다.
    """
    made: list[float] = []
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    while len(made) < dim:
        digest = hashlib.sha256(digest).digest()
        for at in range(0, len(digest), 4):
            if len(made) >= dim:
                break
            (raw,) = struct.unpack("<I", digest[at : at + 4])
            made.append((raw / 4294967296.0) * 2.0 - 1.0)
    length = sum(one * one for one in made) ** 0.5 or 1.0
    return [one / length for one in made]


def _ollama(texts: list[str], dim: int) -> list[list[float]]:
    settings = get_settings()
    base = settings.ollama_base_url.rstrip("/")
    try:
        answer = httpx.post(
            f"{base}/api/embed",
            json={"model": settings.embedding_model, "input": texts},
            timeout=settings.embedding_timeout_s,
        )
        answer.raise_for_status()
        made = answer.json().get("embeddings")
    except httpx.HTTPError as failed:
        raise EmbeddingError(f"임베딩 엔진에 닿지 못했습니다({base}): {failed}") from failed
    if not made or len(made) != len(texts):
        raise EmbeddingError("엔진이 요청한 수만큼 벡터를 주지 않았습니다.")
    for one in made:
        if len(one) != dim:
            raise EmbeddingError(
                f"차원이 다릅니다 — 모델은 {len(one)}, 설정(EMBEDDING_DIM)은 {dim}. "
                "설정을 모델에 맞추고 색인을 다시 만드세요."
            )
    return [list(one) for one in made]


def embed(texts: list[str]) -> list[list[float]]:
    """글 여럿 → 벡터 여럿. **차례가 보존된다.**"""
    if not texts:
        return []
    chosen = backend()
    if chosen == "off":
        raise EmbeddingError("의미 검색이 꺼져 있습니다(EMBEDDING_BACKEND=off).")
    dim = dimension()
    if chosen == "mock":
        return [_mock_vector(one, dim) for one in texts]
    return _ollama(texts, dim)


def embed_one(text: str) -> list[float]:
    return embed([text])[0]


def health() -> dict[str, object]:
    """지금 쓸 수 있나. 화면·`/server/info` 가 「의미 검색 꺼짐」 을 말할 수 있게."""
    chosen = backend()
    if chosen == "off":
        return {"backend": chosen, "ready": False, "note": "꺼져 있습니다."}
    if chosen == "mock":
        return {"backend": chosen, "ready": True, "note": "가짜 벡터입니다 — 시험용."}
    try:
        embed_one("확인")
    except EmbeddingError as failed:
        return {"backend": chosen, "ready": False, "note": str(failed)}
    return {
        "backend": chosen,
        "ready": True,
        "model": get_settings().embedding_model,
        "dim": dimension(),
    }
