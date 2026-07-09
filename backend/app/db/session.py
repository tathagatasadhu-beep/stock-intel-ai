"""
Database session setup (SQLAlchemy async engine).
Reads DATABASE_URL from environment (see .env.example).
"""
import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/stock_intel"
).replace("postgresql://", "postgresql+asyncpg://", 1)

connect_args = {}
if DATABASE_URL.startswith("postgresql+asyncpg://"):
    # Needed when DATABASE_URL points at Supabase's connection pooler (required on
    # platforms like Render whose outbound networking is IPv4-only — Supabase's
    # direct-connection host is IPv6-only). The pooler runs PgBouncer/Supavisor in
    # transaction mode, which doesn't support asyncpg's default server-side
    # prepared-statement caching — disabling it makes every query use an unnamed
    # statement instead, which works correctly under transaction pooling.
    connect_args["statement_cache_size"] = 0

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True, connect_args=connect_args)
SessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db():
    async with SessionLocal() as session:
        yield session
