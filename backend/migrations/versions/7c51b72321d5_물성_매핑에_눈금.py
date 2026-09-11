"""물성 매핑에 눈금

## 왜

사내 항목 「경도」 는 하나인데 문헌은 비커스·브리넬·로크웰·누프가 다른 키다. 매핑이
「경도 → 비커스」 하나뿐이라, 사람이 HRC 60 을 「경도」 에 적으면 비커스 값 검색에
섞여 나온다 — 숫자 크기가 비슷해 눈에 안 띈다(2026-09-12).

## 무엇을 하나

`property_links.scale` — 이 매핑이 어느 눈금의 값에만 해당하는가. 항복강도처럼 눈금이
없는 항목은 비어 있다. 유일 제약이 `(키, 항목, 눈금)` 으로 넓어진다 — 「경도」 는 HRC
와 HRB 로 로크웰에 두 번 이어진다.

기존 「경도 → 비커스」 매핑에 `HV` 를 적고, 브리넬(HB)·로크웰(HRC·HRB)을 더한다.
「경도」 항목이 선언한 눈금(`HV, HB, HRC, HRB, HS`) 가운데 HS(쇼어)는 문헌에 재료
갈래(A·D·OO)로 갈려 있어 여기서 안 잇는다 — 어느 쇼어인지 사람이 정해야 한다.

## 손대지 않은 것

autogenerate 가 `catalog_links` 의 unique 제약 이름 차이를 또 잡았다. 이 이관의 일이
아니라 뺐다(`fc0ec59d424a` 와 같은 판단).

Revision ID: 7c51b72321d5
Revises: f15a011f45bd
Create Date: 2026-09-12 11:20:00

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c51b72321d5"
down_revision: Union[str, Sequence[str], None] = "f15a011f45bd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: 「경도」 항목의 눈금 → 문헌 키.
HARDNESS = (
    ("HV", "mechanical.hardness_vickers"),
    ("HB", "mechanical.hardness_brinell"),
    ("HRC", "mechanical.hardness_rockwell"),
    ("HRB", "mechanical.hardness_rockwell"),
)


def upgrade() -> None:
    op.add_column("property_links", sa.Column("scale", sa.String(length=20), nullable=True))
    op.drop_constraint(op.f("uq_property_links"), "property_links", type_="unique")
    op.create_unique_constraint(
        "uq_property_links", "property_links", ["property_key", "term_id", "scale"]
    )

    bind = op.get_bind()
    term_id = bind.execute(
        sa.text(
            "SELECT t.id FROM vocabulary_terms t JOIN vocabularies v ON v.id = t.vocabulary_id "
            "WHERE v.slug = 'property_item' AND t.value = '경도'"
        )
    ).scalar()
    if term_id is None:
        return
    known = {
        row[0]
        for row in bind.execute(
            sa.text(
                "SELECT key FROM catalog_definitions WHERE key LIKE 'mechanical.hardness_%'"
            )
        ).all()
    }
    # 기존 「경도 → 비커스」 는 HV 의 것이다.
    bind.execute(
        sa.text(
            "UPDATE property_links SET scale = 'HV' "
            "WHERE term_id = :term AND property_key = 'mechanical.hardness_vickers' "
            "AND scale IS NULL"
        ),
        {"term": term_id},
    )
    for scale, key in HARDNESS:
        if key not in known:
            continue
        bind.execute(
            sa.text(
                "INSERT INTO property_links "
                "(id, property_key, term_id, kind, scale, note, created_at) "
                "SELECT gen_random_uuid(), CAST(:key AS varchar), CAST(:term AS uuid), "
                "'same_as', CAST(:scale AS varchar), '눈금별 매핑(이관 7c51b72321d5)', now() "
                "WHERE NOT EXISTS (SELECT 1 FROM property_links "
                "WHERE property_key = CAST(:key AS varchar) AND term_id = CAST(:term AS uuid) "
                "AND scale = CAST(:scale AS varchar))"
            ),
            {"key": key, "term": str(term_id), "scale": scale},
        )


def downgrade() -> None:
    op.drop_constraint("uq_property_links", "property_links", type_="unique")
    op.execute("DELETE FROM property_links WHERE note = '눈금별 매핑(이관 7c51b72321d5)'")
    op.drop_column("property_links", "scale")
    op.create_unique_constraint(
        op.f("uq_property_links"), "property_links", ["property_key", "term_id"]
    )
