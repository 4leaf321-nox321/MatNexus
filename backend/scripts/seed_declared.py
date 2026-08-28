"""개발 DB 에 선언 물성을 임의로 채운다 — **사양 대비 화면을 볼 수 있게.**

    python scripts/seed_declared.py            # 값이 없는 재료만
    python scripts/seed_declared.py --replace  # 있어도 덮는다

## 왜 이름이 맞아야 하나

사양 대비는 **이름**으로 잇는다 — 선언은 기준정보 항목(`탄성계수`)이고 잰 값은 처리
결과의 라벨(`탄성계수`)이라 코드가 안 겹친다. 그래서 여기서 넣는 항목도 기준정보
축(`property_item`)의 값 그대로 쓴다.

개발 DB 에서 실제로 겹치는 것은 **탄성계수** 하나다(잰 값 54건). 나머지 넷
(전단탄성계수·열팽창계수·비열·열전도도)은 인장시험이 안 주므로 화면의 「못 견준
항목」 에 선다 — 그것도 보여야 하는 상태라 함께 넣는다.

**운영에서 돌리지 않는다.** 사람이 문헌·밀시트를 보고 적는 값이고, 지어낸 숫자가
카드의 근거가 되면 안 된다.
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

import app.all_models  # noqa: E402,F401
from app.database import SessionLocal  # noqa: E402
from app.modules.materials.models import Material  # noqa: E402
from sqlalchemy import select  # noqa: E402

#: 항목 → (재료군, 값 범위 SI, 사람이 적는 단위). 물리적으로 그럴듯한 범위를 쓴다 —
#: 화면을 보는 사람이 「이 값이 말이 되나」 를 먼저 묻기 때문이다.
RANGES: dict[str, dict[str, tuple[float, float, str]]] = {
    "Metal": {
        "탄성계수": (195e9, 215e9, "GPa"),
        "전단탄성계수": (75e9, 82e9, "GPa"),
        "열팽창계수": (11e-6, 13e-6, "1/K"),
        "비열": (450.0, 500.0, "J/(kg·K)"),
        "열전도도": (45.0, 60.0, "W/(m·K)"),
    },
    "Plastic": {
        "탄성계수": (1.8e9, 3.2e9, "GPa"),
        "열팽창계수": (60e-6, 90e-6, "1/K"),
        "비열": (1200.0, 1800.0, "J/(kg·K)"),
        "열전도도": (0.2, 0.4, "W/(m·K)"),
    },
}
DEFAULT = RANGES["Metal"]

SOURCES = ("literature", "standard", "datasheet")
REFERENCES = ("KS D 3512 표 3", "ASM Handbook Vol.1", "공급사 자료 2025-03", "사내 물성표 v4")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--replace", action="store_true")
    parser.add_argument("--seed", type=int, default=66)
    args = parser.parse_args()

    random.seed(args.seed)
    filled = skipped = 0
    with SessionLocal() as db:
        for material in db.scalars(select(Material).where(Material.deleted_at.is_(None))):
            if material.declared_properties and not args.replace:
                skipped += 1
                continue
            table = RANGES.get(material.family, DEFAULT)
            # 한 재료가 항목을 다 갖지는 않는다 — **비어 있는 것이 정상**이고,
            # 그래야 「못 견준 항목」 이 화면에서 뜻을 갖는다.
            items = random.sample(sorted(table), k=random.randint(2, len(table)))
            declared = []
            for item in items:
                low, high, unit = table[item]
                value = random.uniform(low, high)
                declared.append(
                    {
                        "item": item,
                        "points": [{"temperature_k": 293.15, "value_si": value}],
                        "input_unit": unit,
                        "source": random.choice(SOURCES),
                        "reference": random.choice(REFERENCES),
                    }
                )
            material.declared_properties = declared
            filled += 1
        db.commit()
    print(f"채움 {filled} · 건너뜀 {skipped}")


if __name__ == "__main__":
    main()
