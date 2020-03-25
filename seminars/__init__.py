# -*- coding: utf-8 -*-
from __future__ import absolute_import
__version__ = '0.1'

#from .website import main
#assert main
from lmfdb.backend.database import PostgresDatabase
db = PostgresDatabase(dbname="beantheory")
assert db

from .categories import categories
assert categories
