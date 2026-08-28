"""장비 커넥터와 수집함 — 장비 PC 가 보낸 파일이 시험이 되기 전까지 사는 자리.

## 왜 시험을 바로 안 만드나

장비 PC 의 수집 에이전트(MatPylon)는 파일이 어느 시편의 것인지 **확신하지
못한다.** 파일 이름에서 뽑은 힌트가 전부다. 그것으로 시편을 만들면 오타 하나가
유령 시편이 된다 — 그래서 에이전트는 시편을 만들지 않고, 서버가 후보를 좁히고,
하나로 안 정해지면 사람이 붙인다. 그 사이 상태가 `pipeline_inbox_items` 에 산다.

## 커넥터는 부서마다 호스트 하나

`UNIQUE(workspace_id, hostname)`. 재설치하면 새로 만들지 않고 기존 것을 돌려준다 —
같은 PC 가 둘로 보이면 관리 화면에서 어느 것이 살아 있는지 알 수 없다.

## sha256 에 인덱스

같은 내용이 이미 있으면 받지 않는다(409). 반입마다 이 검사를 하므로 인덱스가
없으면 수집함이 클수록 반입이 느려진다.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "a7c2e9d41b58"
down_revision: Union[str, Sequence[str], None] = "e51ac62f775e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "pipeline_connectors",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("workspace_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("hostname", sa.String(length=255), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("app_version", sa.String(length=40), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "last_heartbeat",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("created_by_id", sa.UUID(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"],
            ["users.id"],
            name=op.f("fk_pipeline_connectors_created_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_id"],
            ["workspaces.id"],
            name=op.f("fk_pipeline_connectors_workspace_id_workspaces"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_connectors")),
        sa.UniqueConstraint("workspace_id", "hostname", name="uq_pipeline_connectors_host"),
    )
    op.create_index(
        op.f("ix_pipeline_connectors_workspace_id"),
        "pipeline_connectors",
        ["workspace_id"],
        unique=False,
    )

    op.create_table(
        "pipeline_inbox_items",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("connector_id", sa.UUID(), nullable=False),
        sa.Column("source_key", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("size", sa.BigInteger(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("client_path", sa.String(length=1000), nullable=False),
        sa.Column("mtime", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "hints",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("source_path", sa.String(length=500), nullable=True),
        sa.Column("test_type_id", sa.UUID(), nullable=True),
        sa.Column("profile_id", sa.UUID(), nullable=True),
        sa.Column("test_run_id", sa.UUID(), nullable=True),
        sa.Column(
            "candidates",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="[]",
            nullable=False,
        ),
        sa.Column(
            "summary",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id", sa.UUID(), nullable=True),
        sa.Column("discard_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(
            ["connector_id"],
            ["pipeline_connectors.id"],
            name=op.f("fk_pipeline_inbox_items_connector_id_pipeline_connectors"),
        ),
        sa.ForeignKeyConstraint(
            ["profile_id"],
            ["format_profiles.id"],
            name=op.f("fk_pipeline_inbox_items_profile_id_format_profiles"),
        ),
        sa.ForeignKeyConstraint(
            ["resolved_by_id"],
            ["users.id"],
            name=op.f("fk_pipeline_inbox_items_resolved_by_id_users"),
        ),
        sa.ForeignKeyConstraint(
            ["test_run_id"],
            ["test_runs.id"],
            name=op.f("fk_pipeline_inbox_items_test_run_id_test_runs"),
        ),
        sa.ForeignKeyConstraint(
            ["test_type_id"],
            ["test_types.id"],
            name=op.f("fk_pipeline_inbox_items_test_type_id_test_types"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_pipeline_inbox_items")),
    )
    op.create_index(
        op.f("ix_pipeline_inbox_items_connector_id"),
        "pipeline_inbox_items",
        ["connector_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_inbox_items_received_at"),
        "pipeline_inbox_items",
        ["received_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_inbox_items_sha256"),
        "pipeline_inbox_items",
        ["sha256"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_inbox_items_status"),
        "pipeline_inbox_items",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_pipeline_inbox_items_test_run_id"),
        "pipeline_inbox_items",
        ["test_run_id"],
        unique=False,
    )
    op.create_index(
        "ix_pipeline_inbox_status_connector",
        "pipeline_inbox_items",
        ["status", "connector_id"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_pipeline_inbox_status_connector", table_name="pipeline_inbox_items")
    op.drop_index(
        op.f("ix_pipeline_inbox_items_test_run_id"), table_name="pipeline_inbox_items"
    )
    op.drop_index(op.f("ix_pipeline_inbox_items_status"), table_name="pipeline_inbox_items")
    op.drop_index(op.f("ix_pipeline_inbox_items_sha256"), table_name="pipeline_inbox_items")
    op.drop_index(
        op.f("ix_pipeline_inbox_items_received_at"), table_name="pipeline_inbox_items"
    )
    op.drop_index(
        op.f("ix_pipeline_inbox_items_connector_id"), table_name="pipeline_inbox_items"
    )
    op.drop_table("pipeline_inbox_items")
    op.drop_index(
        op.f("ix_pipeline_connectors_workspace_id"), table_name="pipeline_connectors"
    )
    op.drop_table("pipeline_connectors")
