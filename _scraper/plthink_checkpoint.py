"""Transactional PLTHINK resume state; incomplete generations are never published."""
from datetime import datetime, timezone
import json
import sqlite3


class Checkpoint:
    def __init__(self, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db=sqlite3.connect(path, timeout=30)
        self.db.execute('PRAGMA journal_mode=DELETE')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.executescript('''
            CREATE TABLE IF NOT EXISTS runs(id INTEGER PRIMARY KEY, started TEXT, complete INTEGER DEFAULT 0, menu TEXT);
            CREATE TABLE IF NOT EXISTS pages(run INTEGER, brand TEXT, page INTEGER, data TEXT, PRIMARY KEY(run,brand,page));
            CREATE TABLE IF NOT EXISTS details(run INTEGER, id TEXT, listing TEXT, product TEXT, PRIMARY KEY(run,id));
        ''')
        columns={r[1] for r in self.db.execute('PRAGMA table_info(runs)')}
        if 'adapter' not in columns:
            with self.db:self.db.execute('ALTER TABLE runs ADD COLUMN adapter INTEGER DEFAULT 1')
        # Keep old captures for diagnosis; never resume a parser version that
        # accepted replacement characters in Korean names.
        with self.db:self.db.execute('UPDATE runs SET complete=-1 WHERE complete=0 AND adapter<2')
        row=self.db.execute('SELECT id FROM runs WHERE complete=0 AND adapter=2 ORDER BY id DESC LIMIT 1').fetchone()
        if row:self.run=row[0]
        else:
            with self.db:
                self.run=self.db.execute('INSERT INTO runs(started,adapter) VALUES(?,2)',(datetime.now(timezone.utc).isoformat(),)).lastrowid

    def menu(self, brands):
        raw=json.dumps(brands,ensure_ascii=False,sort_keys=True)
        old=self.db.execute('SELECT menu FROM runs WHERE id=?',(self.run,)).fetchone()[0]
        if old is not None and old!=raw:raise ValueError('PLTHINK brand menu changed during this generation')
        with self.db:self.db.execute('UPDATE runs SET menu=? WHERE id=?',(raw,self.run))

    def page(self, brand, n):
        row=self.db.execute('SELECT data FROM pages WHERE run=? AND brand=? AND page=?',(self.run,brand,n)).fetchone()
        return json.loads(row[0]) if row else None

    def save_page(self, brand, n, data):
        raw=json.dumps(data,ensure_ascii=False,sort_keys=True)
        old=self.page(brand,n)
        if old is not None and old!=json.loads(raw):raise ValueError('PLTHINK page checkpoint conflict')
        with self.db:self.db.execute('INSERT OR IGNORE INTO pages VALUES(?,?,?,?)',(self.run,brand,n,raw))

    def detail(self, product):
        row=self.db.execute('SELECT listing,product FROM details WHERE run=? AND id=?',(self.run,product['id'])).fetchone()
        return json.loads(row[1]) if row and json.loads(row[0])==product else None

    def save_detail(self, listing, product):
        if product.get('detail_status')!='verified' or product['id']!=listing['id']:
            raise ValueError('Only matching verified product details can be checkpointed')
        with self.db:self.db.execute('INSERT OR REPLACE INTO details VALUES(?,?,?,?)',
            (self.run,product['id'],json.dumps(listing,ensure_ascii=False),json.dumps(product,ensure_ascii=False)))

    def finish(self):
        with self.db:self.db.execute('UPDATE runs SET complete=1 WHERE id=?',(self.run,))

    def restart(self, brands, changed=None):
        """Preserve history and carry forward only unaffected listing pages."""
        previous=self.run
        with self.db:
            self.db.execute('UPDATE runs SET complete=-1 WHERE id=?',(previous,))
            self.run=self.db.execute('INSERT INTO runs(started,adapter,menu) VALUES(?,2,?)',
                (datetime.now(timezone.utc).isoformat(),json.dumps(brands,ensure_ascii=False,sort_keys=True))).lastrowid
            keep={b['id'] for b in brands}-set(changed) if changed is not None else set()
            for brand in keep:
                self.db.execute('INSERT INTO pages SELECT ?,brand,page,data FROM pages WHERE run=? AND brand=?',(self.run,previous,brand))
            self.db.execute('INSERT INTO details SELECT ?,id,listing,product FROM details WHERE run=?',(self.run,previous))

    def close(self):self.db.close()
