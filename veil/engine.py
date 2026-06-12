from __future__ import annotations

from .audit import AuditLog
from .config import Config
from .pipeline import Pipeline, QueryOutcome


class Veil:
    """Holds one Pipeline per configured database instance, built lazily."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.audit = AuditLog(config.audit_log)
        self._pipelines: dict[str, Pipeline] = {}

    def pipeline(self, database: str | None = None) -> Pipeline:
        view = self.config.instance(database)
        if view.name not in self._pipelines:
            self._pipelines[view.name] = Pipeline(view, self.audit)
        return self._pipelines[view.name]

    async def query(self, sql: str, database: str | None = None) -> QueryOutcome:
        return await self.pipeline(database).query(sql)

    @property
    def default(self) -> str:
        return self.config.default

    def instance_names(self) -> list[str]:
        return self.config.instance_names()

    async def close(self) -> None:
        for p in self._pipelines.values():
            await p.close()
