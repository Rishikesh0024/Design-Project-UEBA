"""Mark synthetic demo datasets separately from uploaded data."""

from alembic import op
import sqlalchemy as sa

revision = "0002_dataset_demo_flag"
down_revision = "0001_platform_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "is_demo" not in {column["name"] for column in inspector.get_columns("datasets")}:
        op.add_column(
            "datasets",
            sa.Column("is_demo", sa.Boolean(), nullable=False, server_default=sa.false()),
        )
    index_names = {index["name"] for index in sa.inspect(op.get_bind()).get_indexes("datasets")}
    if "uq_demo_dataset_version" not in index_names:
        op.create_index(
            "uq_demo_dataset_version",
            "datasets",
            ["version"],
            unique=True,
            postgresql_where=sa.text("is_demo IS TRUE"),
            sqlite_where=sa.text("is_demo = 1"),
        )


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "uq_demo_dataset_version" in {
        index["name"] for index in inspector.get_indexes("datasets")
    }:
        op.drop_index("uq_demo_dataset_version", table_name="datasets")
    if "is_demo" in {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("datasets")
    }:
        op.drop_column("datasets", "is_demo")
