"""Database configuration and session management."""
from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool, AsyncAdaptedQueuePool
from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger("database")


class Base(DeclarativeBase):
    """Base class for all database models."""
    pass


def create_engine():
    """Create database engine with appropriate settings."""
    settings = get_settings()
    
    # Determine if using SQLite or PostgreSQL
    is_sqlite = "sqlite" in settings.database_url.lower()
    
    if is_sqlite:
        # SQLite doesn't support connection pooling the same way
        logger.info("Using SQLite database")
        eng = create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            # SQLite specific: enable foreign keys
            connect_args={"check_same_thread": False} if "aiosqlite" in settings.database_url else {},
        )
        # Enable WAL mode and foreign keys for better concurrency
        @event.listens_for(eng.sync_engine, "connect")
        def _set_sqlite_pragma(dbapi_connection, connection_record):
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        return eng
    else:
        # PostgreSQL with connection pooling
        logger.info(
            f"Using PostgreSQL with pool_size={settings.db_pool_size}, "
            f"max_overflow={settings.db_max_overflow}"
        )
        return create_async_engine(
            settings.database_url,
            echo=settings.db_echo,
            poolclass=AsyncAdaptedQueuePool,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
            pool_timeout=settings.db_pool_timeout,
            pool_pre_ping=True,  # Verify connections before using
            pool_recycle=1800,  # Recycle connections after 30 minutes
        )


# Create async engine
engine = create_engine()

# Create async session factory
async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency to get database session."""
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Database error, rolling back: {e}")
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Initialize database tables."""
    settings = get_settings()
    
    # In production with Alembic, we shouldn't auto-create tables
    if settings.is_production:
        logger.info("Production mode: skipping auto table creation (use Alembic migrations)")
        return
    
    logger.info("Development mode: auto-creating database tables")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """Close database connections."""
    logger.info("Closing database connections")
    await engine.dispose()


async def check_db_connection() -> bool:
    """Check if database connection is healthy."""
    try:
        from sqlalchemy import text
        async with async_session_maker() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        return False
