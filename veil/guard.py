from __future__ import annotations

from dataclasses import dataclass

import pglast
from pglast.visitors import Visitor

WRITE_NODES = {
    "InsertStmt",
    "UpdateStmt",
    "DeleteStmt",
    "MergeStmt",
    "CopyStmt",
    "TruncateStmt",
    "CreateStmt",
    "CreateTableAsStmt",
    "DropStmt",
    "AlterTableStmt",
    "GrantStmt",
    "CreateFunctionStmt",
    "CreateRoleStmt",
    "AlterRoleStmt",
    "DropRoleStmt",
    "VacuumStmt",
    "RefreshMatViewStmt",
    "LockStmt",
    "TransactionStmt",
    "ExecuteStmt",
    "DoStmt",
}

TOP_ALLOWED = {"SelectStmt", "VariableShowStmt", "ExplainStmt"}


@dataclass
class GuardResult:
    allowed: bool
    reason: str | None = None


class _Scan(Visitor):
    def __init__(self) -> None:
        super().__init__()
        self.violations: list[str] = []
        self.relations: set[str] = set()
        self.has_star = False

    def visit(self, ancestors, node):
        name = type(node).__name__
        if name in WRITE_NODES:
            self.violations.append(name.replace("Stmt", "").upper())
        elif name == "SelectStmt":
            if node.intoClause is not None:
                self.violations.append("SELECT INTO")
            if node.lockingClause:
                self.violations.append("row-locking clause (FOR UPDATE/SHARE)")
        elif name == "RangeVar" and node.relname:
            self.relations.add(node.relname.lower())
        elif name == "A_Star":
            self.has_star = True


def check_query(
    sql: str,
    *,
    allow_select_star: bool = False,
    pii_tables: list[str] | tuple[str, ...] = (),
) -> GuardResult:
    sql = sql.strip().rstrip(";").strip()
    if not sql:
        return GuardResult(False, "empty query")

    try:
        stmts = pglast.parse_sql(sql)
    except Exception as exc:
        return GuardResult(False, f"could not parse SQL ({exc})")

    if len(stmts) != 1:
        return GuardResult(False, "only a single statement is allowed per call")

    root = stmts[0].stmt
    top = type(root).__name__
    if top not in TOP_ALLOWED:
        return GuardResult(False, f"only SELECT / SHOW / EXPLAIN are allowed (got {top})")

    if top == "ExplainStmt":
        for opt in root.options or []:
            if (getattr(opt, "defname", "") or "").lower() == "analyze":
                return GuardResult(False, "EXPLAIN ANALYZE executes the query and is not allowed")

    scan = _Scan()
    scan(stmts[0])

    if scan.violations:
        seen = ", ".join(sorted(set(scan.violations)))
        return GuardResult(False, f"write or DDL operation detected: {seen}")

    if scan.has_star and not allow_select_star:
        hit = sorted(scan.relations & {t.lower() for t in pii_tables})
        if hit:
            return GuardResult(
                False,
                f"SELECT * is not allowed on PII table(s): {', '.join(hit)}. "
                "List the columns you need explicitly.",
            )

    return GuardResult(True)
