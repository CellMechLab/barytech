from logging.config import fileConfig
from sqlalchemy import engine_from_config, create_engine, pool
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from alembic import context
from app.models import Base  # Replace with the path to your models
from app.config import settings

# This is the Alembic Config object, which provides access to the values within
# the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Add your model's MetaData object here
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    # Stores the database URL from environment-backed settings to keep Alembic aligned with app runtime config.
    settings_database_url = settings.DATABASE_URL
    # Falls back to alembic.ini only if DATABASE_URL is not provided in environment settings.
    url = settings_database_url or config.get_main_option("sqlalchemy.url")

    # Use a synchronous engine for Alembic migrations
    # Handle both PostgreSQL and SQLite URLs
    if url.startswith("sqlite"):
        connectable = create_engine(url, poolclass=pool.NullPool)
    else:
        connectable = create_engine(
            url.replace("postgresql+asyncpg", "postgresql"),  # Convert async to sync
            poolclass=pool.NullPool,
        )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
