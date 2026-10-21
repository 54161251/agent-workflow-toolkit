from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest
from review_queue import Queue, ReviewError


class ReviewQueueTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name)/'queue.sqlite3'
        self.q = Queue(self.path)
        self.payload = {'kind':'issue_draft','destination':'https://github.com/example/demo',
                        'title':'Handle an empty response','body':'Add a regression test before changing the parser.'}
    def tearDown(self): self.tmp.cleanup()
    def approve(self,row):return self.q.decide(row['id'],row['revision'],row['sha256'],True)
    def test_pending_cannot_run(self):
        row=self.q.propose(self.payload)
        with self.assertRaises(ReviewError):self.q.dry_run(row['id'])
    def test_dry_run_is_local_and_idempotent(self):
        row=self.q.propose(self.payload);self.approve(row)
        first=self.q.dry_run(row['id'])
        self.assertFalse(first['sent']);self.assertEqual(first,self.q.dry_run(row['id']))
        self.assertEqual(1,sum(e['event']=='dry_run_completed' for e in self.q.events(row['id'])))
    def test_edit_invalidates_approval(self):
        row=self.q.propose(self.payload);self.approve(row)
        revised=self.q.revise(row['id'],dict(self.payload,title='A different request'),1)
        self.assertEqual('pending',revised['state'])
        self.assertIsNone(revised['approved_hash'])
        with self.assertRaises(ReviewError):self.q.dry_run(row['id'])
    def test_stale_or_wrong_hash_approval_fails(self):
        row=self.q.propose(self.payload)
        for revision,digest in [(2,row['sha256']),(1,'wrong-hash')]:
            with self.assertRaises(ReviewError):self.q.decide(row['id'],revision,digest,True)
    def test_rejected_cannot_run(self):
        row=self.q.propose(self.payload);self.q.decide(row['id'],1,row['sha256'],False)
        with self.assertRaises(ReviewError):self.q.dry_run(row['id'])
    def test_stale_edit_does_not_overwrite(self):
        row=self.q.propose(self.payload);self.q.revise(row['id'],dict(self.payload,title='New'),1)
        with self.assertRaises(ReviewError):self.q.revise(row['id'],self.payload,1)
        self.assertEqual('New',self.q.show(row['id'])['payload']['title'])
    def test_completed_cannot_be_revised(self):
        row=self.q.propose(self.payload);self.approve(row);self.q.dry_run(row['id'])
        with self.assertRaises(ReviewError):self.q.revise(row['id'],self.payload,1)
    def test_malicious_text_is_stored_as_data(self):
        text="x'); DROP TABLE actions; --"
        row=self.q.propose(dict(self.payload,title=text))
        self.assertEqual(text,self.q.show(row['id'])['payload']['title'])
        self.assertEqual('pending',self.q.propose(self.payload)['state'])
    def test_payload_tampering_detected(self):
        row=self.q.propose(self.payload)
        with closing(sqlite3.connect(self.path)) as db:
            with db:db.execute('UPDATE actions SET payload=? WHERE id=?',('{}',row['id']))
        with self.assertRaises(ReviewError):self.q.show(row['id'])
    def test_unsupported_input_rejected(self):
        bad=[dict(self.payload,destination='http://example.com'),dict(self.payload,destination='https://user:password@example.com'),
             dict(self.payload,kind='send_email'),dict(self.payload,title=''),dict(self.payload,extra=True)]
        for payload in bad:
            with self.assertRaises(ReviewError):self.q.propose(payload)
    def test_persistence_across_clients(self):
        row=self.q.propose(self.payload)
        self.assertEqual(row,Queue(self.path).show(row['id']))
    def test_concurrent_dry_runs_create_one_event(self):
        row=self.q.propose(self.payload);self.approve(row)
        def run(_):return Queue(self.path).dry_run(row['id'])
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
        self.assertEqual(results[0],results[1])
        self.assertEqual(1,sum(e['event']=='dry_run_completed' for e in self.q.events(row['id'])))


if __name__=='__main__':unittest.main()
