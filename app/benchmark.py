import json,tempfile
from pathlib import Path
from .store import Index
from .core import recall,ndcg
with tempfile.TemporaryDirectory() as d:
    idx=Index('sqlite:///'+str(Path(d)/'bench.db'));idx.migrate();idx.ingest('synthetic',json.loads(Path('data/jobs.json').read_text()))
    jobs=idx.jobs();queries=[('python backend','Python Backend Engineer'),('frontend react','Frontend Engineer'),('search retrieval','Search Engineer')]
    report=[]
    for mode in ['keyword','semantic','hybrid']:
        rows=[]
        for query,title in queries:
            relevant={j['id'] for j in jobs if j['title']==title};ranked=[r['job']['id'] for r in idx.search(query,mode,limit=100)['results']]
            rows.append({'query':query,'recall_at_10':recall(ranked,relevant,10),'ndcg_at_10':ndcg(ranked,relevant)})
        report.append({'mode':mode,'queries':rows})
    print(json.dumps({'environment':'native SQLite; deterministic hash fixture, NOT transformer semantic benchmark','results':report},indent=2))
    idx.engine.dispose()
