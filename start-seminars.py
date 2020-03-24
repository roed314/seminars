#!/usr/bin/env python
# -*- coding: utf-8 -*-
# supposed to start via $ sage -python ...
import os, sys
sys.path.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), "lmfdb"))
import lmfdb
from seminars.website import main
main()

