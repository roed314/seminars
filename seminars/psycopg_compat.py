# -*- coding: utf-8 -*-
"""
SQL composition classes and exceptions that track the driver psycodict is
built on.

psycodict is switching from psycopg2 to psycopg3 (roed314/psycodict#88).
Query fragments composed here are executed by psycodict's ``_execute``, so
they must come from the *same* driver psycodict uses -- and both drivers can
be installed at once, so trying imports is not a valid probe.  Instead we key
off psycodict's own re-exported ``SQL``.

Once the psycodict requirement is pinned to a psycopg3-based release, the sql
classes can be imported from psycodict itself (which re-exports them), the
exceptions from ``psycopg``, and this module can be deleted.
"""

import psycodict

_PSYCOPG2 = psycodict.SQL.__module__.startswith("psycopg2")

if _PSYCOPG2:
    from psycopg2 import DatabaseError
    from psycopg2.sql import SQL, Composed, Identifier, Literal, Placeholder
else:
    from psycopg import DatabaseError
    from psycopg.sql import SQL, Composed, Identifier, Literal, Placeholder

__all__ = [
    "SQL",
    "Composed",
    "Identifier",
    "Literal",
    "Placeholder",
    "DatabaseError",
    "copy_table_to_file",
]


def copy_table_to_file(db, tablename, columns, F, sep):
    """
    COPY the given columns of a table TO STDOUT with the given delimiter,
    writing the rows to the open text file ``F``, under either driver.

    (psycopg2 had ``cursor.copy_to``; psycopg3 replaced it with the
    ``cursor.copy`` streaming interface.)
    """
    cur = (getattr(db, "_cursor", None) or db.cursor)()
    if _PSYCOPG2:
        # copy_to quotes the column names itself since psycopg2 2.9; the
        # manual quoting this helper replaced had been broken since then
        cur.copy_to(F, tablename, columns=columns, sep=sep)
    else:
        copyto = SQL("COPY {0} ({1}) TO STDOUT (DELIMITER {2})").format(
            Identifier(tablename),
            SQL(", ").join(map(Identifier, columns)),
            Literal(sep),
        )
        with cur.copy(copyto) as copy:
            for data in copy:
                F.write(bytes(data).decode())
