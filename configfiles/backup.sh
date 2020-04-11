#!/usr/bin/env bash

# have ~/.pgpass in your home directory with permissions rw-------=600
# with the format:
# localhost:5432:beantheory:username:password

set -e
  mkdir -p /scratch/beantheory/
  echo Dumping beantheory
  echo timestamp = `date -u +%Y%m%d-%H%M`
  bdump=/scratch/beantheory/beans`date -u +%Y%m%d-%H%M`.tar
  time pg_dump -U lmfdb --host localhost --clean --if-exists --schema=public -v --file $bdump --format tar beantheory
  echo done
set +e
