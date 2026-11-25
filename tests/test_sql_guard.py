from src.security.sql_guard import sql_is_readonly


def test_select_ok():
    assert sql_is_readonly("SELECT 1")
    assert sql_is_readonly("WITH x AS (SELECT 1) SELECT * FROM x")
    assert sql_is_readonly("DESCRIBE ventas")
    assert sql_is_readonly("SHOW TABLES")


def test_forbidden():
    assert not sql_is_readonly("DELETE FROM ventas")
    assert not sql_is_readonly("DROP TABLE ventas")
    assert not sql_is_readonly("INSERT INTO ventas VALUES (1)")
    assert not sql_is_readonly("PRAGMA database_list")
    assert not sql_is_readonly("")
    assert not sql_is_readonly("UPDATE ventas SET x=1")
