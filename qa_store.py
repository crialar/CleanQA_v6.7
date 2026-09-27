"""RAM-only primary records. SQLite databases, journals and temporary tables stay in memory."""
import json
import sqlite3

class SegmentStore:
    def __init__(self, path=None, on_issue=None):
        self.db = sqlite3.connect(':memory:', timeout=30)
        self.on_issue=on_issue
        self.db.execute('PRAGMA journal_mode=MEMORY')
        self.db.execute('PRAGMA temp_store=MEMORY')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS segments(id INTEGER PRIMARY KEY, sn TEXT, tn TEXT, sl INTEGER, tl INTEGER, payload TEXT);
        CREATE INDEX IF NOT EXISTS segments_source ON segments(sn,id);
        CREATE INDEX IF NOT EXISTS segments_target ON segments(tn,id);
        CREATE TABLE IF NOT EXISTS issues(id INTEGER PRIMARY KEY, category TEXT, segment INTEGER, reference INTEGER, payload TEXT);
        CREATE INDEX IF NOT EXISTS issues_category ON issues(category,id);
        CREATE TABLE IF NOT EXISTS pairs(a INTEGER,b INTEGER,kind TEXT,n INTEGER,PRIMARY KEY(a,b));
        CREATE TABLE IF NOT EXISTS edits(segment INTEGER PRIMARY KEY, value TEXT);
        ''')
    def append(self, seg):
        data={k:v for k,v in seg.items() if not k.endswith('_element')}
        data['_sn']=' '.join(data.get('source_text','').split())
        data['_tn']=' '.join(data.get('target_text','').split())
        data['_sl']=len(data.get('source_text','').strip())
        data['_tl']=len(data.get('target_text','').strip())
        self.db.execute('INSERT INTO segments VALUES(?,?,?,?,?,?)',(data['id'],data['_sn'],data['_tn'],data['_sl'],data['_tl'],json.dumps(data,ensure_ascii=False)))
    def __len__(self):return self.db.execute('SELECT count(*) FROM segments').fetchone()[0]
    def __iter__(self):
        for (raw,) in self.db.execute('SELECT payload FROM segments ORDER BY id'):
            yield json.loads(raw)
    def get(self, sid):
        row=self.db.execute('SELECT payload FROM segments WHERE id=?',(sid,)).fetchone()
        return json.loads(row[0]) if row else None
    def blocks(self, size=128, after=0, candidates=False):
        last=after
        clause="AND sn<>'' AND tn<>''" if candidates else ''
        while True:
            rows=self.db.execute(f'SELECT id,payload FROM segments WHERE id>? {clause} ORDER BY id LIMIT ?', (last,size)).fetchall()
            if not rows:return
            yield [json.loads(raw) for _,raw in rows]
            last=rows[-1][0]
    def add_issue(self, issue):
        sid=issue['segment_id'];seg=self.get(sid)
        if seg:
            issue.update(file=seg.get('file'),local_segment_id=seg.get('local_id'),_target_plain=seg.get('target_text',''))
        ref=self.get(issue.get('reference_segment_id',-1))
        if ref:issue.update(reference_file=ref.get('file'),reference_local_segment_id=ref.get('local_id'))
        self.db.execute('INSERT INTO issues(category,segment,reference,payload) VALUES(?,?,?,?)',(issue['category_id'],sid,issue.get('reference_segment_id'),json.dumps(issue,ensure_ascii=False)))
        if self.on_issue:self.on_issue(issue)
    def commit(self):self.db.commit()
    def close(self):self.db.close()
