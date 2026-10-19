import sqlite3

from mcs.db import make_engine


def test_old_database_gets_source_json(settings):
    settings.data_dir.mkdir(parents=True)
    con = sqlite3.connect(settings.data_dir / "app.db")
    con.execute("CREATE TABLE meeting (id INTEGER PRIMARY KEY, conference_id INTEGER, company VARCHAR NOT NULL)")
    con.commit()
    con.close()
    engine = make_engine(settings)
    with engine.connect() as c:
        cols = {row[1] for row in c.exec_driver_sql("PRAGMA table_info(meeting)")}
    assert "source_json" in cols


def test_old_database_gets_meeting_timezone(settings):
    settings.data_dir.mkdir(parents=True)
    con = sqlite3.connect(settings.data_dir / "app.db")
    con.execute("CREATE TABLE meeting (id INTEGER PRIMARY KEY, conference_id INTEGER, company VARCHAR NOT NULL, "
                "source_json VARCHAR NOT NULL DEFAULT '')")
    con.commit()
    con.close()
    engine = make_engine(settings)
    with engine.connect() as c:
        cols = {row[1] for row in c.exec_driver_sql("PRAGMA table_info(meeting)")}
    assert "timezone" in cols
