"""Reproducible offline demo. Creates only a disposable SQLite database."""
from pathlib import Path
from tempfile import TemporaryDirectory
from review_queue import Queue, ReviewError


def main():
    with TemporaryDirectory() as temp:
        q=Queue(Path(temp)/'demo.sqlite3')
        row=q.propose({'kind':'application_draft','destination':'https://example.com/careers/demo',
                       'title':'Software Engineer application draft','body':'Synthetic demo. No personal data.'})
        try:q.dry_run(row['id'])
        except ReviewError:print('PASS: unapproved draft blocked')
        q.decide(row['id'],row['revision'],row['sha256'],True)
        row=q.revise(row['id'],dict(row['payload'],body='Changed synthetic draft.'),row['revision'])
        try:q.dry_run(row['id'])
        except ReviewError:print('PASS: editing invalidates previous approval')
        q.decide(row['id'],row['revision'],row['sha256'],True)
        result=q.dry_run(row['id'])
        assert result['sent'] is False
        assert q.dry_run(row['id'])==result
        print('PASS: approved dry-run completed; sent=false')
        print('PASS: repeat execution returned the stored result')
        print('Audit events:', ' -> '.join(e['event'] for e in q.events(row['id'])))
        print('No applications, issues, messages, or network requests were sent.')


if __name__=='__main__':main()
