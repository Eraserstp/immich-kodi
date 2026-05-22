import os
import sqlite3

from xbmcaddon import Addon
from xbmcvfs import mkdirs, translatePath


def _db_path():
    profile_path = translatePath(Addon().getAddonInfo("profile"))
    mkdirs(profile_path)
    return os.path.join(profile_path, "tag_filter.db")


def _connect():
    conn = sqlite3.connect(_db_path())
    conn.execute(
        "CREATE TABLE IF NOT EXISTS excluded_tags (tag_id TEXT PRIMARY KEY)"
    )
    return conn


def save_excluded_tag_ids(tag_ids):
    with _connect() as conn:
        conn.execute("DELETE FROM excluded_tags")
        conn.executemany(
            "INSERT INTO excluded_tags(tag_id) VALUES (?)",
            [(str(tag_id),) for tag_id in tag_ids],
        )


def load_excluded_tag_ids():
    with _connect() as conn:
        rows = conn.execute("SELECT tag_id FROM excluded_tags").fetchall()
    return {row[0] for row in rows}

