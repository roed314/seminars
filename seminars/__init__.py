# -*- coding: utf-8 -*-
from __future__ import absolute_import
__version__ = '0.1'

import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "../lmfdb"))

#from .website import main
#assert main
from lmfdb.backend.database import PostgresDatabase
db = PostgresDatabase(dbname="beantheory")
assert db
