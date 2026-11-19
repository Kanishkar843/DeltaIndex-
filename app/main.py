import os,json,secrets
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Literal
from uuid import uuid4
from fastapi import FastAPI,HTTPException,Header,Depends,Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field
from sqlalchemy import text
from .store import Index
from .core import Posting
index=Index()
@asynccontextmanager
async def lifespan(app):
    if not index.pg: index.migrate()
    yield
app=FastAPI(title='DeltaIndex',lifespan=lifespan)
def admin(authorization:str=Header(default='')):
    expected=os.getenv('ADMIN_TOKEN')
    if not expected: raise HTTPException(503,'Set ADMIN_TOKEN to enable mutations')
    if not secrets.compare_digest(authorization,'Bearer '+expected): raise HTTPException(401,'Invalid admin token')
class Batch(BaseModel):
    source:str=Field(default='synthetic',pattern=r'^[a-zA-Z0-9_-]{1,128}$')
    postings:list[Posting]=Field(max_length=2000)
    full_snapshot:bool=False
@app.get('/health')
def health(): return {'status':'ok','embedding_mode':index.embedder.version,'database':index.engine.dialect.name,'cache':'redis' if index.cache else 'native-test-memory'}
@app.post('/ingest/run',dependencies=[Depends(admin)])
def ingest(data:Batch):
    try: return index.ingest(data.source,[p.model_dump() for p in data.postings],data.full_snapshot)
    except ValueError as e: raise HTTPException(422,str(e))
@app.post('/ingest/seed',dependencies=[Depends(admin)])
def seed(): return index.ingest('synthetic',json.loads((Path(__file__).parent.parent/'data/jobs.json').read_text()),True)
@app.get('/ingest/status')
def status():
    with index.engine.connect() as c: return [dict(r)|{'stats':json.loads(r['stats'])} for r in c.execute(text('SELECT * FROM source_runs ORDER BY created_at DESC LIMIT 20')).mappings()]
@app.get('/jobs')
def jobs(limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)): return index.jobs()[offset:offset+limit]
@app.get('/search')
@app.get('/search/explain')
def search(q:str=Query(min_length=1,max_length=500),mode:Literal['keyword','semantic','hybrid']='hybrid',location:str='',remote:bool=False,skills:str='',k:int=Query(60,ge=1,le=200),limit:int=Query(20,ge=1,le=100),offset:int=Query(0,ge=0)):
    return index.search(q,mode,location,remote,tuple(x.strip().lower() for x in skills.split(',') if x.strip()),k,limit,offset)
class Saved(BaseModel): query:str=Field(min_length=1,max_length=500)
@app.post('/saved-searches',dependencies=[Depends(admin)])
def save(data:Saved):
    identity=str(uuid4())
    with index.engine.begin() as c: c.execute(text('INSERT INTO saved_searches VALUES (:id,:q)'),{'id':identity,'q':data.query})
    return {'id':identity}
@app.get('/saved-searches',dependencies=[Depends(admin)])
def saved():
    with index.engine.connect() as c: return [dict(r) for r in c.execute(text('SELECT * FROM saved_searches')).mappings()]
class Feedback(BaseModel): job_id:str; useful:bool
@app.post('/feedback',dependencies=[Depends(admin)])
def feedback(data:Feedback):
    with index.engine.begin() as c: c.execute(text('INSERT INTO feedback_events VALUES (:id,:job,:useful)'),{'id':str(uuid4()),'job':data.job_id,'useful':int(data.useful)})
    return {'saved':True}
static=Path(__file__).parent/'static'
app.mount('/static',StaticFiles(directory=static),name='static')
@app.get('/',include_in_schema=False)
def home(): return FileResponse(static/'index.html')
