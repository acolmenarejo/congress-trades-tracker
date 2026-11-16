#!/usr/bin/env bash
# Commit and push backend/data/congress_trades.db without failing the run
# when another workflow pushed the DB in between (each failed run emails the
# repo owner). A binary SQLite can't be rebased, so on a conflict: take the
# remote DB, re-apply only the tables this workflow owns, and retry.
#
# Usage: backend/tools/push_db.sh "commit message" [!]TABLE[:WHERE] ...
# (table specs as in merge_tables.py; "!" = our rows replace theirs)
set -u
MSG=$1; shift
DB=backend/data/congress_trades.db
git config user.name "github-actions[bot]"
git config user.email "github-actions[bot]@users.noreply.github.com"
for attempt in 1 2 3 4 5 6; do
  git add $DB
  if git diff --cached --quiet; then echo "No changes to commit"; exit 0; fi
  git commit -q -m "$MSG"
  if git pull --rebase -q && git push -q; then exit 0; fi
  git rebase --abort 2>/dev/null || true
  cp $DB /tmp/ours.db
  git fetch -q origin master
  git reset -q --hard origin/master
  python backend/tools/merge_tables.py /tmp/ours.db $DB "$@"
  sleep $((attempt * 5))
done
echo "::error::Could not push the database after 6 attempts"
exit 1
