# This module is used for exporting the database to a version without private information so that other developers can use it.

import os, random, string, secrets, shutil
from lmfdb.backend.utils import IdentifierWrapper, DelayCommit
from psycopg2.sql import SQL, Identifier, Literal

from seminars import db
from seminars.seminar import seminars_search, _selecter as seminar_selecter
from seminars.talk import _selecter as talk_selecter
from seminars.utils import whitelisted_cols
from functools import lru_cache
import time

@lru_cache(maxsize=None)
def mask_email(actual):
    if not actual:
        return actual
    name = ''.join(random.choice(string.ascii_lowercase + string.digits) for _ in range(6))
    return name + "@example.org"

def make_random(col, current, users):
    if col == "live_link":
        if current:
            return "https://mit.zoom.us/j/1234"
        else:
            return ""
    if col in ["owner", "email", "admin"]:
        # admin is used as an email in institutions and as a bool in users
        if current in ["t", "f", r"\N"] or current in users:
            return current
        else:
            return mask_email(current)
    if col == "edited_by":
        # Just throw away edited by info, since it's not currently used
        return "0"
    if col in ["hidden", "password", "affiliation", "admin", "creator", "email_confirmed", "created", "endorser", "seminar_subscriptions", "talk_subscriptions", "subject_admin", "api_access", "order", "curator", "topic_id", "children", "city", "type"]:
        # We already selected only those rows with hidden=False
        # Data in the user table is only recorded for requested users, so we keep their data (including bchashed passwords)
        # Data in the seminar_organizers table is only kept when display is True, so the remainder of the information is public (aside from obfuscated emails)
        # Data in the new_topics table is public
        # Data in the institutions table is public (aside from obfuscated emails)
        return current
    if col == "token":
        return secrets.token_hex(8)
    if col == "api_token":
        return secrets.token_urlsafe(32)
    raise RuntimeError("Need to add randomization code for column %s" % col)

def clear_private_data(filename, safe_cols, approve_row, users, sep):
    tmpfile = filename + ".tmp"
    if os.path.exists(tmpfile):
        raise RuntimeError("Tempfile %s already exists" % tmpfile)
    def _clear(line, all_cols):
        data = line.strip("\n").split(sep)
        assert len(data) == len(all_cols)
        by_col = dict(zip(all_cols, data))
        if approve_row(by_col):
            for i, (col, entry) in enumerate(zip(all_cols, data)):
                if col not in safe_cols:
                    data[i] = make_random(col, entry, users)
            return sep.join(data) + "\n"
        else:
            return ""
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

def write_content_table(data_folder, table, query, selecter, approve_row, users, sep):
    now_overall = time.time()
    print("Exporting %s..." % (table.search_table))
    # The SQL queries for talks and seminars are different
    tablename = table.search_table
    if table in [db.talks, db.seminars]:
        cols = SQL(", ").join(map(IdentifierWrapper, ["id"] + table.search_cols))
        query = SQL(query)
        selecter = selecter.format(cols, cols, IdentifierWrapper(tablename), query)

    searchfile = os.path.join(data_folder, tablename + ".txt")


    header = sep.join(["id"] + table.search_cols) + "\n" + sep.join(["bigint"] + [table.col_type[col] for col in table.search_cols]) + "\n\n"
    table._copy_to_select(selecter, searchfile, header, sep=sep)
    safe_cols = ["id"] + [col for col in table.search_cols if col in whitelisted_cols]
    clear_private_data(searchfile, safe_cols, approve_row, users, sep)

    # do the other files

    from lmfdb.backend.table import _counts_cols, _stats_cols
    from lmfdb.backend.base import _meta_indexes_cols, _meta_constraints_cols, _meta_tables_cols
    statsfile = os.path.join(data_folder, tablename + "_stats.txt")
    countsfile = os.path.join(data_folder, tablename + "_counts.txt")
    indexesfile = os.path.join(data_folder, tablename + "_indexes.txt")
    constraintsfile = os.path.join(data_folder, tablename + "_constraints.txt")
    metafile = os.path.join(data_folder, tablename + "_meta.txt")
    tabledata = [
        # tablename, cols, addid, write_header, filename
        (table.stats.counts, _counts_cols, False, False, countsfile),
        (table.stats.stats, _stats_cols, False, False, statsfile),
    ]

    metadata = [
        ("meta_indexes", "table_name", _meta_indexes_cols, indexesfile),
        ("meta_constraints", "table_name", _meta_constraints_cols, constraintsfile),
        ("meta_tables", "name", _meta_tables_cols, metafile),
    ]

    with DelayCommit(table):
        for tbl, cols, addid, write_header, filename in tabledata:
            if filename is None:
                continue
            now = time.time()
            if addid:
                cols = ["id"] + cols
            cols_wquotes = ['"' + col + '"' for col in cols]
            cur = table._db.cursor()
            with open(filename, "w") as F:
                try:
                    if write_header:
                        table._write_header_lines(F, cols, sep=sep)
                    cur.copy_to(F, tbl, columns=cols_wquotes, sep=sep)
                except Exception:
                    table.conn.rollback()
                    raise
            print(
                "\tExported %s in %.3f secs to %s"
                % (tbl, time.time() - now, filename)
            )

        for tbl, wherecol, cols, filename in metadata:
            if filename is None:
                continue
            now = time.time()
            cols = SQL(", ").join(map(Identifier, cols))
            select = SQL("SELECT {0} FROM {1} WHERE {2} = {3}").format(
                cols,
                Identifier(tbl),
                Identifier(wherecol),
                Literal(table.search_table),
            )
            table._copy_to_select(select, filename, silent=True, sep=sep)
            print(
                "\tExported data from %s in %.3f secs to %s"
                % (tbl, time.time() - now, filename)
            )

        print(
            "Exported %s in %.3f secs"
            % (table.search_table, time.time() - now_overall)
        )

def basic_selecter(table, query=SQL("")):
    return SQL("SELECT {0} FROM {1}{2}").format(
        SQL(", ").join(map(IdentifierWrapper, ["id"] + table.search_cols)),
        IdentifierWrapper(table.search_table),
        query,
    )

def export_dev_db(folder, users, sep="\t"):
    db.copy_to(['new_topics'], folder, sep=sep)
    # We only export the most recent version in case people removed information they didn't want public
    def approve_all(by_col):
        return True
    def approve_none(by_col):
        return False

    # Seminars table
    write_content_table(folder, db.seminars, " WHERE visibility=2 AND deleted=false", seminar_selecter, approve_all, users, sep)

    visible_seminars = set(seminars_search({"visibility": 2}, "shortname"))
    # Talks table
    def approve_row(by_col):
        return by_col["seminar_id"] in visible_seminars
    write_content_table(folder,  db.talks, " WHERE hidden=false AND deleted=false", talk_selecter, approve_row, users, sep)

    user_selecter = basic_selecter(db.users)
    def approve_row(by_col):
        return by_col["email"] in users
    write_content_table(folder,  db.users, "", user_selecter, approve_row, users, sep)

    institutions_selecter = basic_selecter(db.institutions)
    write_content_table(folder,  db.institutions, "", institutions_selecter, approve_all, users, sep)

    new_topics_selecter = basic_selecter(db.new_topics)
    write_content_table(folder, db.new_topics, "", new_topics_selecter, approve_all, users, sep)

    preendorsed_selecter = basic_selecter(db.preendorsed_users)
    write_content_table(folder, db.preendorsed_users, "", preendorsed_selecter, approve_none, users, sep)

    organizers_selecter = basic_selecter(db.seminar_organizers, SQL(" WHERE display=true"))
    write_content_table(folder, db.seminar_organizers, "", organizers_selecter, approve_all, users, sep)

    registrations_selecter = basic_selecter(db.talk_registrations)
    write_content_table(folder, db.talk_registrations, "", registrations_selecter, approve_none, users, sep)


