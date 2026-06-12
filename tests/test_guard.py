from veil.guard import check_query


def test_plain_select_allowed():
    assert check_query("SELECT id, name FROM users").allowed


def test_join_and_aggregate_allowed():
    sql = "SELECT u.id, count(*) FROM users u JOIN orders o ON o.user_id = u.id GROUP BY u.id"
    assert check_query(sql).allowed


def test_cte_select_allowed():
    sql = "WITH recent AS (SELECT * FROM logs WHERE ts > now() - interval '1 day') SELECT count(*) FROM recent"
    assert check_query(sql).allowed


def test_show_allowed():
    assert check_query("SHOW server_version").allowed


def test_explain_allowed_but_analyze_blocked():
    assert check_query("EXPLAIN SELECT 1").allowed
    assert not check_query("EXPLAIN ANALYZE SELECT 1").allowed


def test_writes_blocked():
    for sql in [
        "INSERT INTO t (x) VALUES (1)",
        "UPDATE t SET x = 1",
        "DELETE FROM t",
        "DROP TABLE t",
        "TRUNCATE t",
        "ALTER TABLE t ADD COLUMN y int",
        "CREATE TABLE t (x int)",
        "GRANT SELECT ON t TO public",
    ]:
        assert not check_query(sql).allowed, sql


def test_data_modifying_cte_blocked():
    sql = "WITH w AS (DELETE FROM t RETURNING *) SELECT * FROM w"
    assert not check_query(sql).allowed


def test_multi_statement_blocked():
    assert not check_query("SELECT 1; DROP TABLE t").allowed


def test_select_into_blocked():
    assert not check_query("SELECT * INTO backup FROM users").allowed


def test_locking_clause_blocked():
    assert not check_query("SELECT * FROM users FOR UPDATE").allowed


def test_select_star_on_pii_table_blocked():
    r = check_query("SELECT * FROM contacts", pii_tables=["contacts"])
    assert not r.allowed


def test_select_star_on_non_pii_table_allowed():
    assert check_query("SELECT * FROM metrics", pii_tables=["contacts"]).allowed


def test_select_star_allowed_when_configured():
    assert check_query("SELECT * FROM contacts", allow_select_star=True, pii_tables=["contacts"]).allowed


def test_garbage_blocked():
    assert not check_query("this is not sql").allowed
    assert not check_query("").allowed
