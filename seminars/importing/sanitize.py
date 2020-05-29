# This module is used for exporting the database to a version without private information so that other developers can use it.

import os, random, string, secrets, shutil
from lmfdb.backend.utils import IdentifierWrapper
from psycopg2.sql import SQL
from seminars import db
from seminars.seminar import _selecter as seminar_selecter
from seminars.talk import _selecter as talk_selecter
from seminars.utils import whitelisted_cols
from functools import lru_cache

@lru_cache(maxsize=None)
def mask_email(actual):
    name = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return name + "@example.org"

def make_random(col, current, users):
    if col == "live_link":
        if current:
            return "https://mit.zoom.us/j/1234"
        else:
            return ""
    if col == "owner":
        if current in users:
            return current
        else:
            return mask_email(current)
    if col == "edited_by":
        # Just throw away edited by info, since it's not currently used
        return "0"
    if col == "token":
        return secrets.token_hex(8)
    if col == "api_token":
        return secrets.token_urlsafe(32)
    raise RuntimeError("Need to add randomization code for column %s" % col)

def clear_private_data(filename, safe_cols, users, sep):
    tmpfile = filename + ".tmp"
    if os.path.exists(tmpfile):
        raise RuntimeError("Tempfile %s already exists" % tmpfile)
    def _clear(line, all_cols):
        data = line.strip().split(sep)
        assert len(data) == len(all_cols)
        for i, (entry, col) in enumerate(zip(data, all_cols)):
            if col not in safe_cols:
                data[i] = make_random(col, entry, users)
        return sep.join(data) + "\n"
    with open(filename) as Fin:
        with open(tmpfile, "w") as Fout:
            for i, line in enumerate(Fin):
                if i == 0:
                    all_cols = line.strip().split(sep)
                if i <= 2:
                    Fout.write(line)
                else:
                    Fout.write(_clear(line, all_cols))
    shutil.move(tmpfile, filename)

def write_content_tbl(folder, filename, tbl, query, selecter, sep):
    cols = SQL(", ").join(map(IdentifierWrapper, ["id"] + tbl.search_cols))
    query = SQL(query)
    tbl = IdentifierWrapper(tbl.search_table)
    selecter = selecter.format(cols, cols, tbl, query)
    filename = os.path.join(folder, filename)
    header = sep.join(["id"] + tbl.search_cols) + "\n" + sep.join(["bigint"] + [tbl.col_type[col] for col in tbl.search_cols]) + "\n\n"
    tbl._copy_to_select(selecter, filename, header)
    safe_cols = ["id"] + [col for col in tbl.search_cols if col in whitelisted_cols]
    clear_private_data(filename, safe_cols, users, sep)

def export_dev_db(folder, users, sep="|"):
    # We only export the most recent version in case people removed information they didn't want public

    # Seminars table
    write_content_tbl(folder, "seminars.txt", db.seminars, " WHERE visibility=2 AND deleted=false", seminar_selecter, sep)

    # Talks table
    write_content_tbl(folder, "talks.txt", db.talks, " WHERE hidden=false AND deleted=false", talk_selecter, sep)
    # Also need to remove talks that are part of seminars with visibility < 2

    institutions = list(db.institutions.search())
    new_topics = list(db.new_topics.search())
