"""SQLite storage in data/carfinder.db: foreign cars with their result, PA cache and sightings, Bane's overrides."""
import json
import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "carfinder.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS cars (
    id TEXT PRIMARY KEY, model_key TEXT, data TEXT, result TEXT,
    first_seen REAL, last_seen REAL, price INTEGER);
CREATE TABLE IF NOT EXISTS pa_cache (key TEXT PRIMARY KEY, fetched_at REAL, data TEXT);
CREATE TABLE IF NOT EXISTS pa_seen (
    id TEXT PRIMARY KEY, pa_model TEXT, year INTEGER, price INTEGER, first_seen REAL, last_seen REAL,
    fuel TEXT, gearbox TEXT, kw INTEGER, body TEXT, first_price INTEGER, owner INTEGER);
CREATE TABLE IF NOT EXISTS overrides (
    id TEXT PRIMARY KEY, transport INTEGER, repair INTEGER, origin_proof INTEGER, hidden INTEGER DEFAULT 0,
    carina INTEGER, buy_discount INTEGER, verdict TEXT, verdict_note TEXT, verdict_at REAL, verdict_result TEXT);
CREATE TABLE IF NOT EXISTS runs (started REAL, finished REAL, status TEXT, note TEXT);
CREATE TABLE IF NOT EXISTS paid_runs (
    source TEXT, model_key TEXT, attempted REAL, finished REAL, cars TEXT, PRIMARY KEY (source, model_key));
"""

# Columns added after a table was first made, in SCHEMA order: an older database gets them without losing rows.
NEW_COLUMNS = {
    "overrides": {"carina": "INTEGER", "buy_discount": "INTEGER", "verdict": "TEXT", "verdict_note": "TEXT",
                  "verdict_at": "REAL", "verdict_result": "TEXT"},
    "pa_seen": {"fuel": "TEXT", "gearbox": "TEXT", "kw": "INTEGER", "body": "TEXT", "first_price": "INTEGER",
                "owner": "INTEGER"},
}


def connect(path=None):
    path = path or DB_PATH
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    for table, new_columns in NEW_COLUMNS.items():
        columns = [row["name"] for row in conn.execute(f"PRAGMA table_info({table})")]
        for column, kind in new_columns.items():
            if column in columns:
                continue
            try:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {kind}")
                if column == "first_price":
                    # the price was overwritten on every sighting until now; the latest is the nearest to the first
                    conn.execute("UPDATE pa_seen SET first_price = price")
                conn.commit()
            except sqlite3.OperationalError as error:   # the page and a scan opened it together; the other added it
                if "duplicate column name" not in str(error):
                    raise
    return conn


def cached_pa(conn, key, max_age_s):
    row = conn.execute("SELECT fetched_at, data FROM pa_cache WHERE key = ?", (key,)).fetchone()
    if row and time.time() - row["fetched_at"] < max_age_s:
        return json.loads(row["data"])
    return None


def drop_old_pa_cache(conn, version):
    """Every cache key starts with the version that wrote it; rows of other versions are never read again."""
    conn.execute("DELETE FROM pa_cache WHERE key NOT LIKE ?", (f"[{version},%",))
    conn.commit()


def store_pa(conn, key, cars, pa_model):
    now = time.time()
    with conn:   # cache row and sightings are written together or not at all
        conn.execute("INSERT OR REPLACE INTO pa_cache VALUES (?, ?, ?)", (key, now, json.dumps(cars)))
        for car in cars:
            # first_price is the first price PA gave and is never overwritten: later it shows a cut
            conn.execute(
                "INSERT INTO pa_seen (id, pa_model, year, price, first_seen, last_seen, fuel, gearbox, kw, body, "
                "first_price, owner) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(id) DO UPDATE SET price = excluded.price, last_seen = excluded.last_seen, "
                "fuel = excluded.fuel, gearbox = excluded.gearbox, kw = excluded.kw, body = excluded.body, "
                "owner = excluded.owner, first_price = COALESCE(pa_seen.first_price, excluded.first_price)",
                (car["id"], pa_model, car["year"], car["price"], now, now, car.get("fuel"), car.get("gearbox"),
                 car.get("kw"), car.get("body"), car["price"], car.get("owner")))


def save_car(conn, car, result, model_key):
    now = time.time()
    conn.execute(
        "INSERT INTO cars VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(id) DO UPDATE SET "
        "data = excluded.data, result = excluded.result, last_seen = excluded.last_seen, price = excluded.price",
        (car["id"], model_key, json.dumps(car), json.dumps(result), now, now, car["price"]))
    conn.commit()


def saved_reading(conn, car_id):
    """What Haiku read in this ad on an earlier scan, or None."""
    row = conn.execute("SELECT data FROM cars WHERE id = ?", (car_id,)).fetchone()
    return json.loads(row["data"]).get("ai") if row else None


def overrides(conn):
    return {row["id"]: dict(row) for row in conn.execute("SELECT * FROM overrides")}


def set_override(conn, car_id, transport=None, repair=None, origin_proof=None, hidden=0, carina=None, buy_discount=None,
                 verdict=None, verdict_note=None, verdict_at=None, verdict_result=None):
    conn.execute("INSERT OR REPLACE INTO overrides (id, transport, repair, origin_proof, hidden, carina, buy_discount, "
                 "verdict, verdict_note, verdict_at, verdict_result) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                 (car_id, transport, repair, origin_proof, hidden, carina, buy_discount, verdict, verdict_note,
                  verdict_at, verdict_result))
    conn.commit()


def entry_of(row):
    return {"data": json.loads(row["data"]), "result": json.loads(row["result"]), "first_seen": row["first_seen"],
            "last_seen": row["last_seen"], "model_key": row["model_key"]}


def cars(conn, seen_after):
    rows = conn.execute("SELECT * FROM cars WHERE last_seen >= ? AND result != 'null'", (seen_after,))
    return [entry_of(row) for row in rows]


def car(conn, car_id):
    """One priced car as cars() gives it, or None."""
    row = conn.execute("SELECT * FROM cars WHERE id = ? AND result != 'null'", (car_id,)).fetchone()
    return entry_of(row) if row else None


def log_run(conn, started, status, note):
    conn.execute("INSERT INTO runs VALUES (?, ?, ?, ?)", (started, time.time(), status, note))
    conn.commit()


def paid_run(conn, source, model_key):
    """Last attempt, last success and the cars it brought, for a source paid per run; None before the first attempt."""
    row = conn.execute("SELECT attempted, finished, cars FROM paid_runs WHERE source = ? AND model_key = ?",
                       (source, model_key)).fetchone()
    if not row:
        return None
    return {"attempted": row["attempted"], "finished": row["finished"], "cars": json.loads(row["cars"] or "[]")}


def mark_attempt(conn, source, model_key):
    conn.execute("INSERT INTO paid_runs (source, model_key, attempted) VALUES (?, ?, ?) "
                 "ON CONFLICT(source, model_key) DO UPDATE SET attempted = excluded.attempted",
                 (source, model_key, time.time()))
    conn.commit()


def store_run(conn, source, model_key, cars):
    conn.execute("UPDATE paid_runs SET finished = ?, cars = ? WHERE source = ? AND model_key = ?",
                 (time.time(), json.dumps(cars), source, model_key))
    conn.commit()


def last_runs(conn, limit=5):
    return [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY started DESC LIMIT ?", (limit,))]
