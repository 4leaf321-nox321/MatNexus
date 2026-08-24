"""밀시트 값은 시료에 붙는다

`samples.declared_properties` — 로트마다 다른 값(항복강도·인장강도·연신율).

재료의 같은 이름 칸과 **층이 다르다**(ADR 0016). 밀시트는 「이 로트가 규격에
맞나」를 증명하는 문서지 물리 상수표가 아니다(EN 10204 3.1) — 그 값을 재료에
적으면 첫 로트의 값이 그 Grade 전체의 값이 되고, 두 번째 로트가 들어오는 순간
둘 중 하나가 조용히 진다.

기본값을 `[]` 로 둔다. `null` 과 「없다」를 구별할 이유가 없고, 구별하면 읽는
쪽마다 그 갈래를 써야 한다.

Revision ID: 9efc6878b742
Revises: 198f219ea68e
Create Date: 2026-08-25 08:34:56.501753

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "9efc6878b742"
down_revision: Union[str, Sequence[str], None] = "198f219ea68e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "samples",
        sa.Column(
            "declared_properties",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("samples", "declared_properties")
