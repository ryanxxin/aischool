import os
import json
import logging
import asyncio
from typing import Optional

logger = logging.getLogger(__name__)


class ReportStore:
    """Simple PostgreSQL-backed store for LLM-generated reports.

    Tries to use `asyncpg` (async). If not installed, falls back to psycopg2 executed
    in a thread using asyncio.to_thread to avoid blocking the event loop.
    """

    def __init__(self):
        self.pg_host = os.getenv("PG_HOST")
        self.pg_port = int(os.getenv("PG_PORT", "5432"))
        self.pg_db = os.getenv("PG_DB")
        self.pg_user = os.getenv("PG_USER")
        self.pg_password = os.getenv("PG_PASSWORD")

        self._conn = None
        self._asyncpg = None
        self._psycopg2 = None

    async def init(self):
        # try asyncpg first
        try:
            import asyncpg

            self._asyncpg = asyncpg
            self._conn = await asyncpg.connect(
                host=self.pg_host,
                port=self.pg_port,
                user=self.pg_user,
                password=self.pg_password,
                database=self.pg_db,
            )
            await self._ensure_table_async()
            logger.info("ReportStore: connected via asyncpg")
            return
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.debug("asyncpg not available or connect failed: %s", exc)

        # fallback to psycopg2
        try:
            import psycopg2
            from psycopg2.extras import Json

            self._psycopg2 = psycopg2
            # test connection synchronously in thread
            def _sync_connect():
                return psycopg2.connect(
                    host=self.pg_host,
                    port=self.pg_port,
                    user=self.pg_user,
                    password=self.pg_password,
                    dbname=self.pg_db,
                )

            self._conn = await asyncio.to_thread(_sync_connect)
            await asyncio.to_thread(self._ensure_table_sync)
            logger.info("ReportStore: connected via psycopg2 (sync fallback)")
            return
        except Exception as exc:  # pragma: no cover - optional dependency
            logger.error("No PostgreSQL driver available or connect failed: %s", exc)
            self._conn = None

    async def _ensure_table_async(self):
        q = """
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            alert_id TEXT,
            sensor_id TEXT,
            level TEXT,
            metric TEXT,
            value DOUBLE PRECISION,
            threshold DOUBLE PRECISION,
            alert_ts TIMESTAMP,
            llm_summary TEXT,
            raw JSONB,
            created_at TIMESTAMP DEFAULT now()
        )
        """
        await self._conn.execute(q)

    def _ensure_table_sync(self):
        q = """
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            alert_id TEXT,
            sensor_id TEXT,
            level TEXT,
            metric TEXT,
            value DOUBLE PRECISION,
            threshold DOUBLE PRECISION,
            alert_ts TIMESTAMP,
            llm_summary TEXT,
            raw JSONB,
            created_at TIMESTAMP DEFAULT now()
        )
        """
        cur = self._conn.cursor()
        cur.execute(q)
        self._conn.commit()
        cur.close()

    async def save_report(self, alert: dict, llm_summary: Optional[str] = None) -> Optional[int]:
        """Save alert + llm_summary into reports table. Returns inserted id if possible."""
        if not self._conn:
            logger.warning("ReportStore not initialized; skipping save")
            return None

        alert_id = alert.get("id")
        sensor_id = alert.get("sensor_id")
        level = alert.get("level")
        metric = alert.get("metric")
        value = alert.get("value")
        threshold = alert.get("threshold")
        alert_ts = alert.get("timestamp")

        raw = json.dumps(alert)

        if self._asyncpg:
            try:
                rec = await self._conn.fetchrow(
                    "INSERT INTO reports(alert_id, sensor_id, level, metric, value, threshold, alert_ts, llm_summary, raw) VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9) RETURNING id",
                    alert_id,
                    sensor_id,
                    level,
                    metric,
                    value,
                    threshold,
                    alert_ts,
                    llm_summary,
                    json.loads(raw),
                )
                return rec["id"]
            except Exception as exc:
                logger.error("Failed to insert report (async): %s", exc)
                return None

        if self._psycopg2:
            def _sync_insert():
                cur = self._conn.cursor()
                try:
                    cur.execute(
                        "INSERT INTO reports(alert_id, sensor_id, level, metric, value, threshold, alert_ts, llm_summary, raw) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                        (
                            alert_id,
                            sensor_id,
                            level,
                            metric,
                            value,
                            threshold,
                            alert_ts,
                            llm_summary,
                            json.loads(raw),
                        ),
                    )
                    rid = cur.fetchone()[0]
                    self._conn.commit()
                    return rid
                except Exception as exc:  # pragma: no cover - fallback path
                    logger.error("Failed to insert report (sync): %s", exc)
                    self._conn.rollback()
                    return None
                finally:
                    cur.close()

            return await asyncio.to_thread(_sync_insert)

        logger.warning("No DB driver available to save report")
        return None

    async def close(self):
        try:
            if self._asyncpg and self._conn:
                await self._conn.close()
            elif self._psycopg2 and self._conn:
                await asyncio.to_thread(self._conn.close)
        except Exception:
            pass
