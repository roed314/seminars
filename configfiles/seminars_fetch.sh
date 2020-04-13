#!/usr/bin/env bash
date

for branch in stable master; do
  if [ -d "/home/mathseminars/seminars-git-${branch}" ]; then
    pushd /home/mathseminars/seminars-git-$branch
    git fetch
    git checkout origin/$branch -f
    popd
  fi
done





