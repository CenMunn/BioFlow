import hashlib
import json
import sqlite3
import sys
from pathlib import Path

original,restored=map(Path,sys.argv[1:3])
report={'tables':{},'files_checked':0,'passed':True}
for name in ('skills','revisions','drafts','sources','imports','sessions'):
    def rows(root):
        with sqlite3.connect(root/'database'/'center.sqlite') as conn:
            return conn.execute(f'SELECT id,body FROM {name} ORDER BY id').fetchall()
    left,right=rows(original),rows(restored)
    assert left==right,name
    report['tables'][name]=len(left)
for directory in ('skills','drafts','imports'):
    for p in (original/directory).rglob('*'):
        if p.is_file():
            q=restored/p.relative_to(original)
            assert q.is_file() and hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256(q.read_bytes()).digest(),str(p)
            report['files_checked']+=1
assert (restored/'admin.json').read_bytes()==(original/'admin.json').read_bytes()
report['configuration_preserved']=True
print(json.dumps(report))
