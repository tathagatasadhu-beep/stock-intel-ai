"""
Tiny idempotent schema-repair helper, run at startup by BOTH the web service
(app/main.py) and the batch job (scripts/refresh_universe.py).

`Base.metadata.create_all` only creates missing TABLES — it does nothing for a column
added to an ORM model whose table already existed in production (e.g. Stock.asset_type,
added for portfolio/ETF support after `stocks` was already live). Without this, whichever
service deploys first after such a change would 500 on nearly every request the moment it
tries to query the new column, until the OTHER service happened to run and add it —
`refresh_universe.py` only runs once a day, so that gap could be the whole day. Both
callers running this makes schema safety independent of deploy order.

Safe to call on every startup/run — the ALTER attempt is expected to fail with "column
already exists" on every call after the first, which is caught and ignored.
"""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.orm import Base


async def ensure_schema(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Its own separate transaction so a "column already exists" failure here — the normal
    # case on every run after the first — can't poison a later statement in the same
    # transaction (Postgres aborts the whole transaction after any statement error until
    # it's rolled back).
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE stocks ADD COLUMN asset_type VARCHAR DEFAULT 'stock'"))
    except Exception:  # noqa: BLE001 - expected once the column already exists
        pass

    # news_articles.url was globally unique, but the same wire article can legitimately
    # be relevant news for more than one ticker (confirmed live: MPC's on-demand refresh
    # 500'd on a duplicate-key IntegrityError for a URL already stored against a different
    # stock) — app/db/orm.py::NewsArticle now declares uniqueness on (stock_id, url)
    # instead. No existing row can violate the new constraint (it's strictly looser than
    # the old one), so this is safe to run against data that already has the old
    # constraint in place.
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE news_articles DROP CONSTRAINT IF EXISTS news_articles_url_key"))
    except Exception:  # noqa: BLE001 - e.g. already dropped, or SQLite (no-op there anyway)
        pass
    try:
        async with engine.begin() as conn:
            await conn.execute(text("ALTER TABLE news_articles ADD CONSTRAINT uq_news_stock_url UNIQUE (stock_id, url)"))
    except Exception:  # noqa: BLE001 - expected once the constraint already exists
        pass
