# -*- coding: utf-8 -*-
from __future__ import absolute_import

__version__ = "0.1"

import os, sys

sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../lmfdb"))

# from .website import main
# assert main
from lmfdb.backend import db
assert db

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


for tname in db.tablenames:
    db[tname].log_db_change = nothing
    db[tname].add_column = are_you_REALLY_sure(db[tname].add_column)
    db[tname].drop_column = are_you_REALLY_sure(db[tname].drop_column)
