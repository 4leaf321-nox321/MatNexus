"""계산이 무엇으로 나왔는지 — **소급이 안 되는 기록.**

이 저장소는 재현을 위해 레시피 스냅샷·플러그인 버전·적합의 경계와 초기값까지
남긴다. 그 논리의 나머지 절반이 이것이다 — `scipy` 가 바뀌면 같은 데이터·같은
플러그인 버전에서 다른 파라미터가 나올 수 있다.

오늘 만든 것이 어느 scipy 로 계산됐는지는 **오늘 적어야 안다.**
"""

from __future__ import annotations

from matcore import runtime


class Test기록:
    def test_계산을_바꿀_수_있는_것을_담는다(self) -> None:
        """**여기 없는 것은 바뀌어도 결과가 안 바뀐다** 는 뜻이다."""
        got = runtime.manifest()
        assert {"python", "implementation", "numpy", "scipy", "pyarrow"} <= set(got)
        assert got["python"][0].isdigit()
        assert got["scipy"] != "없음", "적합의 최적화기가 여기 있다"

    def test_같은_환경이면_같은_지문이다(self) -> None:
        assert runtime.manifest()["digest"] == runtime.manifest()["digest"]
        assert len(runtime.manifest()["digest"]) == 16

    def test_없는_라이브러리도_사실로_적는다(self) -> None:
        """빈칸으로 두면 **"안 적혔다" 와 구별이 안 된다.**"""
        assert runtime._installed("이런패키지는없다") == "없음"

    def test_경로나_사용자_이름은_안_담는다(self) -> None:
        """재현에 안 쓰이고 그 자체로 정보다."""
        joined = " ".join(runtime.manifest().values()).lower()
        for leak in ("c:\\\\", "/home/", "users", "appdata"):
            assert leak not in joined


class Test비교:
    def test_기록이_없으면_같다고_안_한다(self) -> None:
        """**모르는 것과 같은 것은 다르다.** 기록이 없는 결과는 이 기능이 생기기
        전에 만들어진 것이고, 그때 무엇이었는지는 알 길이 없다."""
        got = runtime.manifest()
        assert runtime.same(got, None) is False
        assert runtime.same(None, got) is False
        assert runtime.same({}, {}) is False

    def test_지문이_다르면_다른_환경이다(self) -> None:
        got = runtime.manifest()
        assert runtime.same(got, got) is True
        assert runtime.same(got, {**got, "digest": "0" * 16}) is False
