"""물성 항목 축 이름을 「사내 물성 항목」 으로

세 층(문헌 물성 · 사내 항목 · 시험이 재는 값) 가운데 이 축이 어느 것인지 이름만 보고
알 수 있어야 한다(2026-09-12). 관리자가 이미 다른 이름을 붙였으면 손대지 않는다.

Revision ID: 4f60297a1774
Revises: 27ea22e88a43
Create Date: 2026-09-12 09:40:00

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "4f60297a1774"
down_revision: str | Sequence[str] | None = "27ea22e88a43"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE vocabularies SET label = '사내 물성 항목' "
        "WHERE slug = 'property_item' AND label = '물성 항목'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE vocabularies SET label = '물성 항목' "
        "WHERE slug = 'property_item' AND label = '사내 물성 항목'"
    )
