"""프로파일이 메타를 **시험 칸**과 **식별자**에 잇는다.

둘을 갈라 둔 이유는 되돌릴 수 있는 실수와 없는 실수의 차이다. 시험자를 잘못
채우면 고치면 되지만, 곡선이 남의 재료에 붙으면 그 시험은 만들 때 그 시편 id 에
묶여 있어 칸을 고쳐 되돌릴 수 없다. 그래서 **시험 칸은 채우고, 식별자는 짚기만
한다.**
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.modules.tests.legacy_profiles import LEGACY_TENSILE_DEFINITION
from matcore.readers import profile as profiles

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
WITH_UNITS = FIXTURES / "legacy_tensile.mtet"


def made(**meta: Any) -> bytes:
    """메타 키-값과 최소한의 표를 가진 JSON."""
    doc: dict[str, Any] = {
        **meta,
        "curve": [
            {"disp": 0.0, "load": 0.0},
            {"disp": 0.1, "load": 400.0},
        ],
    }
    return json.dumps(doc, ensure_ascii=False).encode("utf-8")


BASE: dict[str, Any] = {
    "match": {"extensions": [".json"], "header_any": ["load"]},
    "tables": {"mode": "all", "include": "^curve$"},
    "columns": {
        "disp": {"channel": "displacement", "unit": "mm"},
        "load": {"channel": "force", "unit": "N"},
    },
}


class Test선언이_없으면:
    """**하위 호환.** 이 자리가 없는 프로파일은 전과 똑같이 동작해야 한다.

    전에는 이것을 `LEGACY_TENSILE_DEFINITION` 으로 확인했는데, 그 정의에
    `record` 를 더하면서 **전제가 사라졌다** — 「선언이 없을 때」 를 보려면
    선언이 없는 정의로 봐야 한다. CI 가 그것을 잡았다.
    """

    def bare(self) -> dict[str, Any]:
        """옛 정의 그대로에서 **새 자리만 뺀 것.**"""
        return {
            key: value
            for key, value in LEGACY_TENSILE_DEFINITION.items()
            if key not in ("record", "identity", "conditions", "material", "sample")
        }

    def test_아무것도_안_채운다(self) -> None:
        parsed = profiles.apply(self.bare(), WITH_UNITS.read_bytes())
        assert parsed.record == {}
        assert parsed.identity == {}
        assert parsed.conditions == {}
        assert parsed.material == {}
        assert parsed.sample == {}

    def test_곡선과_요약값은_그대로다(self) -> None:
        """새 자리를 더한 것이 **원래 하던 일**을 흔들면 안 된다."""
        parsed = profiles.apply(self.bare(), WITH_UNITS.read_bytes())
        assert {channel.key for channel in parsed.curves[0].channels} == {
            "displacement",
            "force",
            "specimen_width",
        }
        assert any(value.key == "legacy_tensile_strength" for value in parsed.summary)


class Test옛_앱_프로파일이_제자리로_보낸다:
    """다섯이 전부 원문 보관에 있었다 — 보관은 글자로만 남아 비교도 통계도
    안 되는데, 그 값들이 갈 제자리가 이미 있었다."""

    def parsed(self) -> Any:
        return profiles.apply(LEGACY_TENSILE_DEFINITION, WITH_UNITS.read_bytes())

    def test_시험_기록을_채운다(self) -> None:
        assert self.parsed().record == {
            "operator": "홍길동",
            "instrument": "Zwick Z100",
            # 옛 앱은 `2024-03-11 09:20:00` 으로 적는다. 형식을 선언해 뒀다.
            "tested_at": "2024-03-11T09:20:00",
        }

    def test_시험_조건을_채운다(self) -> None:
        """인장 종류가 `sensor_type`·`testing_group` 을 선언하고 있다."""
        assert self.parsed().conditions == {
            "sensor_type": "makroXtens",
            "testing_group": "판재 인장",
        }

    def test_시편을_짚어_준다(self) -> None:
        assert self.parsed().identity == {"specimen_seq_no": "1"}

    def test_원문도_남는다(self) -> None:
        """자리를 옮겼다고 **파일에 뭐라고 적혀 있었는지**를 잃으면 안 된다."""
        metadata = self.parsed().metadata
        assert metadata["operator"] == "홍길동"
        assert metadata["rundate"] == "2024-03-11 09:20:00"


class Test시험_칸:
    def test_선언한_칸을_읽는다(self) -> None:
        rule = {**BASE, "record": {"작업자": {"field": "operator"}}}
        parsed = profiles.apply(rule, made(작업자="홍길동"))
        assert parsed.record == {"operator": "홍길동"}

    def test_원문이_메타에_그대로_남는다(self) -> None:
        """가져가 버리면 "파일에는 뭐라고 적혀 있었나" 에 못 답한다 — 그건 원본
        보관의 뜻을 반쯤 없앤다."""
        rule = {**BASE, "record": {"작업자": {"field": "operator"}}}
        parsed = profiles.apply(rule, made(작업자="홍길동"))
        assert "홍길동" in parsed.metadata.values()

    def test_보관_목록이_있어도_원문이_남는다(self) -> None:
        """**여기가 빠져 있었다.** 위 시험은 보관 목록이 **아예 없는**
        프로파일로 확인한 것이라 조건이 달랐다 — 화면으로 만든 프로파일은
        목록을 항상 적는다(비어 있더라도). 그때 `record` 가 읽은 라벨은 목록에
        안 들어가므로 원문이 사라졌다.

        시험일에서 특히 나쁘다. 형식이 안 맞아 못 읽으면 칸도 비고 원문도 없어서
        **파일에 무엇이 적혀 있었는지 알 방법이 아예 사라진다.**
        """
        rule = {
            **BASE,
            "metadata": [],  # 화면이 「전부 버림」으로 만든 모양
            "record": {"작업자": {"field": "operator"}},
            "identity": {"재료": {"field": "material_grade"}},
        }
        parsed = profiles.apply(rule, made(작업자="홍길동", 재료="SECC"))
        assert parsed.metadata.get("작업자") == "홍길동"
        assert parsed.metadata.get("재료") == "SECC"
        # 채우는 일은 그대로 된다.
        assert parsed.record == {"operator": "홍길동"}

    def test_못_읽은_날짜도_원문은_남는다(self) -> None:
        """칸은 비워 두더라도 **파일에 뭐라고 적혀 있었는지는 남아야** 사람이
        형식을 고칠 수 있다."""
        rule = {
            **BASE,
            "metadata": [],
            "record": {"일자": {"field": "tested_at", "format": "%Y-%m-%d"}},
        }
        parsed = profiles.apply(rule, made(일자="05/06/2020"))
        assert "tested_at" not in parsed.record
        assert parsed.metadata.get("일자") == "05/06/2020"

    def test_빈_값은_안_적은_것이다(self) -> None:
        """`Unknown` 을 그대로 넣으면 시험자가 `Unknown` 인 기록이 생기고, 그
        뒤로는 그 칸이 비어 있었다는 사실을 알 수 없다."""
        rule = {
            **BASE,
            "record": {"작업자": {"field": "operator"}, "장비": {"field": "instrument"}},
        }
        parsed = profiles.apply(rule, made(작업자="Unknown", 장비="  "))
        assert parsed.record == {}


class Test재료와_시료:
    """**다른 DB 에서 통째로 넘어온 파일**을 위한 자리.

    재료의 두께·밀도·푸아송비, 시료의 제조사·생산일까지 한 파일에 들어 있는
    경우가 있다. 그런데 **업로드가 이것을 쓰면 안 된다** — 재료 아래 시험이
    100건이면 같은 칸이 100번 덮어써지고, 그중 하나만 옛 값이어도 카드와 덱이
    조용히 바뀐다. 시편 치수는 시험 하나가 시편 하나를 보므로 「빈 칸만 채운다」
    로 막을 수 있었지만 재료는 그렇게 못 막는다.

    그래서 `identity` 와 같은 자리에 둔다 — **읽어서 넘기기만** 하고, 실제로
    쓰는 것은 이관 경로뿐이다.
    """

    def profile(self) -> dict[str, Any]:
        return {
            **BASE,
            "material": {
                "Thickness": {"field": "spec_thickness", "unit": "mm"},
                "Density": {"field": "density", "unit": "tonne/mm3"},
                "Poisson": {"field": "poisson_ratio"},
                "Family": {"field": "family"},
            },
            "sample": {
                "Maker": {"field": "manufacturer"},
                "Made on": {"field": "production_date", "format": "%Y/%m/%d"},
            },
        }

    def test_값과_단위를_함께_낸다(self) -> None:
        parsed = profiles.apply(
            self.profile(),
            made(
                Thickness="1.2",
                Density="7.85e-9",
                Poisson="0.3",
                Family="Metal",
                Maker="포스코",
            ),
        )
        assert parsed.material == {
            "spec_thickness": "1.2",
            "density": "7.85e-9",
            "poisson_ratio": "0.3",
            "family": "Metal",
        }
        # **단위가 값과 함께 가야 한다.** JSON 에는 단위 줄이 아예 없어서, 안
        # 보내면 읽는 쪽이 기본값(mm · tonne/mm3)으로 본다.
        assert parsed.material_units == {
            "spec_thickness": "mm",
            "density": "tonne/mm3",
        }
        assert parsed.sample == {"manufacturer": "포스코"}

    def test_값에_붙어_온_단위도_받는다(self) -> None:
        """`"1.2 mm"` 처럼 한 칸에 붙어 오는 파일이 있다. 조건과 같은 규칙이다."""
        profile = self.profile()
        del profile["material"]["Thickness"]["unit"]
        parsed = profiles.apply(profile, made(Thickness="1.2 mm"))
        assert parsed.material == {"spec_thickness": "1.2"}
        assert parsed.material_units == {"spec_thickness": "mm"}

    def test_프로파일이_적은_단위가_이긴다(self) -> None:
        parsed = profiles.apply(self.profile(), made(Thickness="0.0012 m"))
        assert parsed.material_units["spec_thickness"] == "mm"
        # **붙어 온 단위를 떼어 낸다.** 통째로 넘기면 숫자로 못 읽는다.
        assert parsed.material["spec_thickness"] == "0.0012"

    def test_생산일을_짐작하지_않는다(self) -> None:
        """`05/06/2020` 은 6월 5일일 수도 5월 6일일 수도 있다. **둘 다
        그럴듯해서** 화면 어디에도 티가 안 난다."""
        parsed = profiles.apply(self.profile(), made(**{"Made on": "2020/06/05"}))
        assert parsed.sample["production_date"].startswith("2020-06-05")

        parsed = profiles.apply(self.profile(), made(**{"Made on": "05-06-2020"}))
        assert "production_date" not in parsed.sample
        assert any("날짜 형식" in said for said in parsed.warnings)

    def test_원문도_남는다(self) -> None:
        """「파일에는 뭐라고 적혀 있었나」 에 답할 수 있어야 한다."""
        parsed = profiles.apply(self.profile(), made(Thickness="1.2", Maker="포스코"))
        # 보관 키는 라벨의 슬러그다 — `_keep_sources` 가 그렇게 담는다.
        assert parsed.metadata["thickness"] == "1.2"
        assert parsed.metadata["maker"] == "포스코"

    def test_빈_값은_안_적은_것이다(self) -> None:
        parsed = profiles.apply(
            self.profile(), made(Thickness="", Density="Unknown", Maker="-")
        )
        assert parsed.material == {}
        assert parsed.sample == {}


class Test날짜:
    def test_ISO_는_그냥_읽는다(self) -> None:
        rule = {**BASE, "record": {"일자": {"field": "tested_at"}}}
        parsed = profiles.apply(rule, made(일자="2024-03-11T09:00:00"))
        assert parsed.record["tested_at"] == "2024-03-11T09:00:00"

    def test_형식을_적으면_그것으로_읽는다(self) -> None:
        rule = {**BASE, "record": {"일자": {"field": "tested_at", "format": "%d/%m/%Y"}}}
        parsed = profiles.apply(rule, made(일자="05/06/2020"))
        assert parsed.record["tested_at"].startswith("2020-06-05")

    def test_형식을_모르면_짐작하지_않는다(self) -> None:
        """`05/06/2020` 은 6월 5일일 수도 5월 6일일 수도 있다. **둘 다 그럴듯해서**
        잘못 읽어도 화면 어디에도 티가 안 난다."""
        rule = {**BASE, "record": {"일자": {"field": "tested_at", "format": "%Y-%m-%d"}}}
        parsed = profiles.apply(rule, made(일자="05/06/2020"))
        assert "tested_at" not in parsed.record
        assert any("일자" in warning for warning in parsed.warnings)


class Test키를_만들_때:
    def test_한글_라벨을_지우지_않는다(self) -> None:
        """전에는 한글이 통째로 지워져 전부 `unnamed` 이 됐고, **두 개가 있으면
        하나가 조용히 덮였다.** 국산 장비와 사내 내보내기는 라벨이 한글이다."""
        rule = {**BASE, "metadata": ["작업자", "재료"]}
        parsed = profiles.apply(rule, made(작업자="홍길동", 재료="SECC"))
        assert parsed.metadata["작업자"] == "홍길동"
        assert parsed.metadata["재료"] == "SECC"

    def test_영문_라벨은_전과_같다(self) -> None:
        """바꾼 것이 옛 프로파일의 키를 흔들면 안 된다 — 저장된
        `source_metadata` 를 읽는 화면이 못 찾게 된다."""
        rule = {**BASE, "metadata": ["Instrument name", "Tan(delta)"]}
        parsed = profiles.apply(rule, made(**{"Instrument name": "Z100", "Tan(delta)": "0.1"}))
        assert parsed.metadata["instrument_name"] == "Z100"
        assert parsed.metadata["tan_delta"] == "0.1"

    def test_겹치면_덮지_않는다(self) -> None:
        """다르게 적힌 두 라벨이 같은 키로 줄어들 수 있다(`A-1` 과 `A 1`).
        그때 조용히 하나를 잃으면, 잃었다는 사실조차 알 수 없다."""
        rule = {**BASE, "metadata": ["A-1", "A 1"]}
        parsed = profiles.apply(rule, made(**{"A-1": "먼저", "A 1": "나중"}))
        assert sorted(parsed.metadata.values()) == ["나중", "먼저"]


class Test시험_조건:
    """시험 조건은 **시험 종류마다 다르다** — 인장은 속도·예하중이고 DMA 는
    진폭이다. 그래서 이 층은 무엇이 유효한지 모르고, 원문을 그대로 넘긴다.
    """

    def test_값과_단위를_함께_낸다(self) -> None:
        """단위를 안 보내면 읽는 쪽이 정의의 SI 로 본다. 정의가 `m/s` 인데
        파일이 `mm/min` 이면 **6만 배**이고 숫자는 그럴듯하다."""
        rule = {**BASE, "conditions": {"속도": {"field": "speed_elastic", "unit": "mm/min"}}}
        parsed = profiles.apply(rule, made(속도="5"))
        assert parsed.conditions == {"speed_elastic": "5"}
        assert parsed.condition_units == {"speed_elastic": "mm/min"}

    def test_값에_붙어_온_단위를_읽는다(self) -> None:
        """`5 mm/min` 처럼 한 칸에 붙여 주는 장비가 실재한다."""
        rule = {**BASE, "conditions": {"속도": {"field": "speed_elastic"}}}
        parsed = profiles.apply(rule, made(속도="5 mm/min"))
        assert parsed.conditions == {"speed_elastic": "5"}
        assert parsed.condition_units == {"speed_elastic": "mm/min"}

    def test_프로파일이_적은_단위가_이긴다(self) -> None:
        """소프트웨어 설정이 바뀌어 표기가 달라진 파일이 올 수 있다. 그때
        사람이 프로파일에서 못 바로잡으면 고칠 자리가 없다."""
        rule = {**BASE, "conditions": {"속도": {"field": "speed_elastic", "unit": "mm/s"}}}
        parsed = profiles.apply(rule, made(속도="5 mm/min"))
        assert parsed.conditions == {"speed_elastic": "5"}
        assert parsed.condition_units == {"speed_elastic": "mm/s"}

    def test_단위가_없으면_안_보낸다(self) -> None:
        """글자 조건(센서 종류)에는 단위가 없다. 억지로 넣으면 검증이 막는다."""
        rule = {**BASE, "conditions": {"센서": {"field": "sensor_type"}}}
        parsed = profiles.apply(rule, made(센서="makroXtens"))
        assert parsed.conditions == {"sensor_type": "makroXtens"}
        assert parsed.condition_units == {}

    def test_빈_값은_안_보낸다(self) -> None:
        rule = {**BASE, "conditions": {"속도": {"field": "speed_elastic"}}}
        assert profiles.apply(rule, made(속도="Unknown")).conditions == {}

    def test_선언이_없으면_비어_있다(self) -> None:
        """**하위 호환.** 기존 프로파일은 이 자리가 없다."""
        parsed = profiles.apply(BASE, made(속도="5"))
        assert parsed.conditions == {}
        assert parsed.condition_units == {}


class Test식별자:
    def test_짚어_주기만_한다(self) -> None:
        rule = {
            **BASE,
            "identity": {
                "재료": {"field": "material_grade"},
                "로트": {"field": "sample_lot_no"},
            },
        }
        parsed = profiles.apply(rule, made(재료="SECC", 로트="LOT-A"))
        assert parsed.identity == {"material_grade": "SECC", "sample_lot_no": "LOT-A"}
        # **채우지 않는다.** 곡선과 섞이지 않아야 한다.
        assert parsed.record == {}

    def test_식별자에는_날짜_형식이_없다(self) -> None:
        """식별자는 이름이지 시각이 아니다. 형식을 적어도 안 쓴다."""
        rule = {**BASE, "identity": {"재료": {"field": "material_grade", "format": "%Y"}}}
        parsed = profiles.apply(rule, made(재료="2024"))
        assert parsed.identity == {"material_grade": "2024"}
