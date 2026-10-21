"""Local approval-workflow prototype. No network or external-action adapter."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Any
from urllib.parse import urlsplit
import uuid


class ReviewError(ValueError):
    pass


def canonical(value: dict[str, Any]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def validate(value: dict[str, Any]) -> str:
    if not isinstance(value, dict) or set(value) != {'kind', 'destination', 'title', 'body'}:
        raise ReviewError('Expected exactly kind, destination, title, and body.')
    if value['kind'] not in ('issue_draft', 'application_draft'):
        raise ReviewError('Unsupported draft kind.')
    for key, limit in [('destination', 500), ('title', 200), ('body', 10000)]:
        text = value[key]
        if not isinstance(text, str) or not text.strip() or len(text) > limit:
            raise ReviewError(f'Invalid {key}.')
        if any(ord(c) < 32 and c not in '\n\t' for c in text):
            raise ReviewError(f'Control character in {key}.')
    target = urlsplit(value['destination'])
    if target.scheme != 'https' or not target.hostname or target.username or target.password:
        raise ReviewError('Destination must be an HTTPS URL without embedded credentials.')
    return canonical(value)


def fingerprint(payload: str) -> str:
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()


class Queue:
    """SQLite serializes transitions; approval binds to a revision and hash."""
    def __init__(self, path: str | Path):
        self.path = str(path)
        with self._db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS actions (
                    id TEXT PRIMARY KEY, revision INTEGER NOT NULL,
                    payload TEXT NOT NULL, sha256 TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('pending','approved','rejected','completed')),
                    approved_revision INTEGER, approved_hash TEXT, result TEXT
                );
                CREATE TABLE IF NOT EXISTS events (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    action_id TEXT NOT NULL, revision INTEGER NOT NULL,
                    event TEXT NOT NULL, at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    FOREIGN KEY(action_id) REFERENCES actions(id)
                );
            ''')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _get(db, action_id):
        row = db.execute('SELECT * FROM actions WHERE id=?', (action_id,)).fetchone()
        if row is None:
            raise ReviewError('Action not found.')
        if fingerprint(row['payload']) != row['sha256']:
            raise ReviewError('Stored payload fingerprint does not match.')
        return row

    @staticmethod
    def _event(db, action_id, revision, event):
        db.execute('INSERT INTO events(action_id,revision,event) VALUES(?,?,?)', (action_id, revision, event))

    def propose(self, payload):
        text = validate(payload)
        action_id = uuid.uuid4().hex
        with self._db() as db:
            db.execute('INSERT INTO actions(id,revision,payload,sha256,state) VALUES(?,?,?,?,?)',
                       (action_id, 1, text, fingerprint(text), 'pending'))
            self._event(db, action_id, 1, 'proposed')
        return self.show(action_id)

    def show(self, action_id):
        with self._db() as db:
            row = dict(self._get(db, action_id))
        row['payload'] = json.loads(row['payload'])
        row['result'] = json.loads(row['result']) if row['result'] else None
        return row

    def revise(self, action_id, payload, expected_revision):
        text = validate(payload)
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._get(db, action_id)
            if row['state'] == 'completed':
                raise ReviewError('Completed drafts cannot be revised; propose a new draft.')
            if row['revision'] != expected_revision:
                raise ReviewError('Stale revision. Review the current draft.')
            revision = row['revision'] + 1
            db.execute('''UPDATE actions SET revision=?,payload=?,sha256=?,state='pending',
                          approved_revision=NULL,approved_hash=NULL,result=NULL WHERE id=?''',
                       (revision, text, fingerprint(text), action_id))
            self._event(db, action_id, revision, 'revised_approval_invalidated')
        return self.show(action_id)

    def decide(self, action_id, revision, sha256, approve):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._get(db, action_id)
            if row['state'] != 'pending':
                raise ReviewError('Only pending drafts can be reviewed.')
            if row['revision'] != revision or row['sha256'] != sha256:
                raise ReviewError('Approval does not match the current draft.')
            state = 'approved' if approve else 'rejected'
            db.execute('UPDATE actions SET state=?,approved_revision=?,approved_hash=? WHERE id=?',
                       (state, revision if approve else None, sha256 if approve else None, action_id))
            self._event(db, action_id, revision, state)
        return self.show(action_id)

    def dry_run(self, action_id):
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            row = self._get(db, action_id)
            if row['state'] == 'completed':
                return json.loads(row['result'])
            if (row['state'] != 'approved' or row['approved_revision'] != row['revision']
                    or row['approved_hash'] != row['sha256']):
                raise ReviewError('A matching approval is required before a dry-run.')
            # This adapter has no side effects outside this database transaction.
            # Real HTTP execution needs its own retry/outbox/idempotency design.
            result = {'action_id': action_id, 'revision': row['revision'], 'sha256': row['sha256'],
                      'adapter': 'local_dry_run', 'sent': False,
                      'draft': json.loads(row['payload'])}
            db.execute("UPDATE actions SET state='completed',result=? WHERE id=?", (canonical(result), action_id))
            self._event(db, action_id, row['revision'], 'dry_run_completed')
        return result

    def events(self, action_id):
        with self._db() as db:
            self._get(db, action_id)
            return [dict(r) for r in db.execute('SELECT * FROM events WHERE action_id=? ORDER BY sequence', (action_id,))]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--db', default='review_queue.sqlite3')
    sub = p.add_subparsers(dest='command', required=True)
    propose = sub.add_parser('propose'); propose.add_argument('file', type=Path)
    revise = sub.add_parser('revise'); revise.add_argument('id'); revise.add_argument('file', type=Path)
    revise.add_argument('--revision', required=True, type=int)
    for name in ('show', 'events', 'dry-run'):
        parser = sub.add_parser(name); parser.add_argument('id')
    for name in ('approve', 'reject'):
        parser = sub.add_parser(name); parser.add_argument('id')
        parser.add_argument('--revision', required=True, type=int)
        parser.add_argument('--sha256', required=True)
    a = p.parse_args()
    try:
        q = Queue(a.db)
        if a.command == 'propose': output = q.propose(json.loads(a.file.read_text(encoding='utf-8')))
        elif a.command == 'revise': output = q.revise(a.id, json.loads(a.file.read_text(encoding='utf-8')), a.revision)
        elif a.command in ('approve','reject'): output = q.decide(a.id,a.revision,a.sha256,a.command == 'approve')
        elif a.command == 'dry-run': output = q.dry_run(a.id)
        elif a.command == 'events': output = q.events(a.id)
        else: output = q.show(a.id)
        print(json.dumps(output,ensure_ascii=False,indent=2))
    except (ReviewError, OSError, json.JSONDecodeError, sqlite3.Error, ValueError, TypeError):
        p.exit(2, 'Request failed: check the input, database path, revision, and approval state.\n')


if __name__ == '__main__':
    main()
