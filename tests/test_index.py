import json
from pathlib import Path
import pytest
from app.store import Index
from app.core import rrf,recall,ndcg,Posting
@pytest.fixture
def idx(tmp_path):
    i=Index('sqlite:///'+str(tmp_path/'index.db')); i.migrate();return i
@pytest.fixture
def data(): return json.loads(Path('data/jobs.json').read_text())
def test_incremental_ingest(idx,data):
    assert idx.ingest('demo',data,True)['created']==120
    assert idx.ingest('demo',data,True)['embeddings']==0
    data[0]['description']='A changed python description'
    assert idx.ingest('demo',data,True)['embeddings']==1
    assert idx.ingest('demo',data[1:],True)['deactivated']==1
    assert len(idx.jobs())==119
def test_cache_invalidation_filter_and_injection(idx,data):
    idx.ingest('demo',data)
    assert idx.search('python')['cache']=='miss'
    assert idx.search('python')['cache']=='hit'
    data[0]['title']='Changed engineer';idx.ingest('demo',data)
    assert idx.search('python')['cache']=='miss'
    assert all(r['job']['remote'] for r in idx.search('python',remote=True)['results'])
    idx.search("'; DROP TABLE jobs; --")
    assert len(idx.jobs())==120
    assert len(idx.search('python',limit=3,offset=3)['results'])==3
def test_rrf_and_metrics():
    assert rrf([['a','b'],['b','a']])['a']==pytest.approx(1/61+1/62)
    assert recall(['a','x'],{'a','b'},2)==.5
    assert ndcg(['a','b'],{'a','b'})==1
    assert ndcg([],set())==0
def test_atomic_validation_and_duplicate_ids(idx,data):
    with pytest.raises(ValueError): idx.ingest('demo',[data[0],dict(data[1],title='')])
    assert idx.jobs()==[]
    with pytest.raises(ValueError): idx.ingest('demo',[data[0],data[0]])
def test_embedding_version_refresh(idx,data):
    idx.ingest('demo',data[:2]);idx.embedder.version='fixture-hash-v2'
    assert idx.ingest('demo',data[:2])['embeddings']==2
