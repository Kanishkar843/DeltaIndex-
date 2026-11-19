import os, json, hashlib, time
from datetime import datetime,timezone
from sqlalchemy import create_engine, text
from .core import Posting,content,digest,Embedder,rrf,preferences,tokens

class Index:
    def __init__(self,url=None,mode=None,redis_url=None):
        self.engine=create_engine(url or os.getenv('DATABASE_URL','sqlite:///./deltaindex.db'))
        self.pg=self.engine.dialect.name=='postgresql'
        self.embedder=Embedder(mode or os.getenv('EMBEDDING_MODE','fixture'))
        self.cache=None; self.local_cache={}
        redis_url=redis_url or os.getenv('REDIS_URL')
        if redis_url:
            import redis
            self.cache=redis.Redis.from_url(redis_url,decode_responses=True,socket_timeout=2)
    def migrate(self):
        vector_type='vector' if self.pg else 'TEXT'
        with self.engine.begin() as c:
            if self.pg: c.execute(text('CREATE EXTENSION IF NOT EXISTS vector'))
            c.execute(text(f'CREATE TABLE IF NOT EXISTS jobs (id VARCHAR(64) PRIMARY KEY, source VARCHAR(128) NOT NULL, external_id VARCHAR(128) NOT NULL, content_hash VARCHAR(64) NOT NULL, payload TEXT NOT NULL, searchable TEXT NOT NULL, embedding {vector_type} NOT NULL, model VARCHAR(200) NOT NULL, active INTEGER NOT NULL, updated_at VARCHAR(40) NOT NULL, UNIQUE(source,external_id))'))
            c.execute(text('CREATE INDEX IF NOT EXISTS jobs_source_active ON jobs(source,active)'))
            if self.pg: c.execute(text("CREATE INDEX IF NOT EXISTS jobs_fts ON jobs USING gin(to_tsvector('english',searchable))"))
            c.execute(text('CREATE TABLE IF NOT EXISTS source_runs (id VARCHAR(64) PRIMARY KEY, source VARCHAR(128), stats TEXT, created_at VARCHAR(40))'))
            c.execute(text('CREATE TABLE IF NOT EXISTS index_state (id INTEGER PRIMARY KEY, revision INTEGER NOT NULL)'))
            c.execute(text('INSERT INTO index_state (id,revision) VALUES (1,0) ON CONFLICT (id) DO NOTHING'))
            c.execute(text('CREATE TABLE IF NOT EXISTS saved_searches (id VARCHAR(64) PRIMARY KEY, query TEXT NOT NULL)'))
            c.execute(text('CREATE TABLE IF NOT EXISTS feedback_events (id VARCHAR(64) PRIMARY KEY, job_id VARCHAR(64), useful INTEGER)'))
    def revision(self):
        with self.engine.connect() as c: return c.execute(text('SELECT revision FROM index_state WHERE id=1')).scalar_one()
    def ingest(self,source,postings,full_snapshot=False):
        from uuid import uuid4
        validated=[Posting.model_validate(p) for p in postings]
        if len({p.external_id for p in validated})!=len(validated): raise ValueError('Duplicate external IDs in snapshot')
        stats={'created':0,'updated':0,'unchanged':0,'deactivated':0,'embeddings':0}
        stamp=datetime.now(timezone.utc).isoformat(); seen=set()
        with self.engine.begin() as c:
            # Serialize writers to keep snapshots and revision invalidation atomic on PostgreSQL.
            if self.pg: c.execute(text('SELECT revision FROM index_state WHERE id=1 FOR UPDATE'))
            for p in validated:
                identity=hashlib.sha256((source+'\0'+p.external_id).encode()).hexdigest(); seen.add(identity)
                old=c.execute(text('SELECT content_hash,model,active FROM jobs WHERE id=:id'),{'id':identity}).mappings().first()
                changed=not old or old['content_hash']!=digest(p) or old['model']!=self.embedder.version
                if not changed and old['active']:
                    stats['unchanged']+=1;continue
                embedding=self.embedder.encode(content(p));stats['embeddings']+=1
                params={'id':identity,'source':source,'external_id':p.external_id,'hash':digest(p),'payload':json.dumps(p.model_dump()),'searchable':content(p),'embedding':json.dumps(embedding),'model':self.embedder.version,'stamp':stamp}
                value='CAST(:embedding AS vector)' if self.pg else ':embedding'
                c.execute(text(f'INSERT INTO jobs VALUES (:id,:source,:external_id,:hash,:payload,:searchable,{value},:model,1,:stamp) ON CONFLICT(id) DO UPDATE SET content_hash=excluded.content_hash,payload=excluded.payload,searchable=excluded.searchable,embedding=excluded.embedding,model=excluded.model,active=1,updated_at=excluded.updated_at'),params)
                stats['updated' if old else 'created']+=1
            if full_snapshot:
                rows=c.execute(text('SELECT id FROM jobs WHERE source=:source AND active=1'),{'source':source}).scalars().all()
                for identity in rows:
                    if identity not in seen:
                        c.execute(text('UPDATE jobs SET active=0,updated_at=:stamp WHERE id=:id'),{'id':identity,'stamp':stamp});stats['deactivated']+=1
            if stats['created']+stats['updated']+stats['deactivated']: c.execute(text('UPDATE index_state SET revision=revision+1 WHERE id=1'))
            c.execute(text('INSERT INTO source_runs VALUES (:id,:source,:stats,:stamp)'),{'id':str(uuid4()),'source':source,'stats':json.dumps(stats),'stamp':stamp})
        self.local_cache.clear()
        return stats
    def jobs(self):
        with self.engine.connect() as c:
            return [{**json.loads(r['payload']),'id':r['id'],'updated_at':r['updated_at']} for r in c.execute(text('SELECT * FROM jobs WHERE active=1 ORDER BY id')).mappings()]
    def search(self,query,mode='hybrid',location='',remote=False,skills=(),k=60,limit=20,offset=0):
        key='delta:'+str(self.revision())+':'+hashlib.sha256(json.dumps([query.lower().strip(),mode,location,remote,sorted(skills),k,limit,offset]).encode()).hexdigest()
        cached=self.cache.get(key) if self.cache else self.local_cache.get(key)
        if cached: return {**json.loads(cached),'cache':'hit'}
        all_jobs=self.jobs(); eligible={j['id']:j for j in all_jobs if (not location or location.lower() in j['location'].lower()) and (not remote or j['remote'])}
        if self.pg:
            with self.engine.connect() as c:
                lex=c.execute(text("SELECT id,ts_rank_cd(to_tsvector('english',searchable),plainto_tsquery('english',:q)) AS score FROM jobs WHERE active=1 AND to_tsvector('english',searchable) @@ plainto_tsquery('english',:q) ORDER BY score DESC,id"),{'q':query}).mappings().all()
                vec=c.execute(text('SELECT id,1-(embedding <=> CAST(:v AS vector)) AS score FROM jobs WHERE active=1 AND model=:model ORDER BY score DESC,id'),{'v':json.dumps(self.embedder.encode(query)),'model':self.embedder.version}).mappings().all()
        else:
            q=set(tokens(query)); v=self.embedder.encode(query)
            lex=sorted([{'id':j['id'],'score':len(q&set(tokens(' '.join([j['title'],j['description'],*j['skills']]))))} for j in all_jobs],key=lambda r:(-r['score'],r['id']))
            lex=[r for r in lex if r['score']>0]
            with self.engine.connect() as c: rows=c.execute(text('SELECT id,embedding FROM jobs WHERE active=1')).mappings().all()
            vec=sorted([{'id':r['id'],'score':sum(a*b for a,b in zip(v,json.loads(r['embedding'])))} for r in rows],key=lambda r:(-r['score'],r['id']))
        lex=[r for r in lex if r['id'] in eligible];vec=[r for r in vec if r['id'] in eligible]
        lr={r['id']:i+1 for i,r in enumerate(lex)};vr={r['id']:i+1 for i,r in enumerate(vec)}
        fused=rrf([list(lr),list(vr)],k) if mode=='hybrid' else {r['id']:float(r['score']) for r in (lex if mode=='keyword' else vec)}
        results=[]
        for identity,base in fused.items():
            job=eligible[identity]; features=preferences(job,skills,remote)
            results.append({'job':job,'lexical_rank':lr.get(identity),'vector_rank':vr.get(identity),'base_score':base,'preferences':features,'score':base+sum(features.values())})
        results.sort(key=lambda r:(-r['score'],r['job']['id']))
        payload={'results':results[offset:offset+limit],'total':len(results),'mode':mode,'embedding_model':self.embedder.version,'lexical_engine':'PostgreSQL ts_rank_cd' if self.pg else 'native test token overlap','cache':'miss'}
        if self.cache: self.cache.setex(key,120,json.dumps(payload))
        else: self.local_cache[key]=json.dumps(payload)
        return payload
