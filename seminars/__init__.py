# -*- coding: utf-8 -*-
from __future__ import absolute_import

__version__ = "0.1"

import os
import sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../psycodict"))

# from .website import main
# assert main
from psycodict.database import PostgresDatabase
import __main__
startQ =  getattr(__main__, '__file__').endswith("start-seminars.py") if hasattr(__main__, '__file__') else False
from .config import Configuration
db = PostgresDatabase(config=Configuration(writeargstofile=startQ, readargs=startQ))
from psycodict.searchtable import PostgresSearchTable

# Have to make sure that changes aren't logged using the LMFDB's logging mechanism.
def nothing(self, *args, **kwds):
    pass


def are_you_REALLY_sure(func):
    def call(*args, **kwargs):
        ok = input(
            "Are you REALLY sure you want to do call %s?\nYou will most likely break the website if you don't change the code first!! (yes/no)"
            % (func)
        )
        if not (ok and ok.lower() == "yes"):
            return
        else:
            return func(*args, **kwargs)

    return call


def update(self, query, changes, resort=False, restat=False, commit=True):
    return PostgresSearchTable.update(
        self, query=query, changes=changes, resort=resort, restat=restat, commit=commit
    )


def count(self, query, groupby=None, record=False):
    return PostgresSearchTable.count(self, query=query, groupby=groupby, record=record)


def insert_many(self, data, resort=False, reindex=False, restat=False):
    return PostgresSearchTable.insert_many(
        self, data=data, resort=resort, reindex=reindex, restat=restat
    )


for tname in db.tablenames:
    db[tname].log_db_change = nothing
    # db[tname].add_column = are_you_REALLY_sure(db[tname].add_column)
    db[tname].drop_column = are_you_REALLY_sure(db[tname].drop_column)
    db[tname].update = update.__get__(db[tname])
    db[tname].count = count.__get__(db[tname])
    db[tname].insert_many = insert_many.__get__(db[tname])
