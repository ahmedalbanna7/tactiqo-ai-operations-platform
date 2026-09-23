"""Alembic environment for platform-owned PostgreSQL truth tables."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from tactiqo.agents.catalog.infrastructure import tables as agent_catalog_tables  # noqa: F401
from tactiqo.ai.infrastructure import tables as ai_tables  # noqa: F401
from tactiqo.artifacts.infrastructure import tables as artifact_tables  # noqa: F401
from tactiqo.authorization.infrastructure import tables as authorization_tables  # noqa: F401
from tactiqo.chat.infrastructure import tables as chat_tables  # noqa: F401
from tactiqo.identity.infrastructure import tables as identity_tables  # noqa: F401
from tactiqo.integrations.infrastructure import tables as integration_tables  # noqa: F401
from tactiqo.jobs.infrastructure import tables as job_tables  # noqa: F401
from tactiqo.knowledge.infrastructure import tables as knowledge_tables  # noqa: F401
from tactiqo.shared.infrastructure.database import Base
from tactiqo.shared.infrastructure.settings import Settings
from tactiqo.tools.infrastructure import tables as tool_tables  # noqa: F401

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

settings = Settings()
sync_url = settings.database_url.get_secret_value().replace(
    "postgresql+asyncpg://",
    "postgresql+psycopg://",
)
config.set_main_option("sqlalchemy.url", sync_url.replace("%", "%%"))
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations without a live connection."""
    context.configure(
        url=sync_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run transactional migrations against the configured database."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
