import hashlib, json, math, re
from collections import Counter
from datetime import datetime, timezone
from pydantic import BaseModel, Field, ConfigDict

def tokens(s): return re.findall(r'[a-z0-9]+',s.lower())
class Posting(BaseModel):
    model_config=ConfigDict(extra='forbid')
    external_id:str=Field(min_length=1,max_length=128)
    title:str=Field(min_length=1,max_length=200)
    employer:str=Field(min_length=1,max_length=200)
    description:str=Field(min_length=1,max_length=10000)
    location:str=Field(min_length=1,max_length=200)
    remote:bool=False
    seniority:str=Field(default='mid',max_length=40)
    skills:list[str]=Field(default_factory=list,max_length=30)
    synthetic:bool=True

def content(p): return ' '.join([p.title,p.employer,p.description,p.location,p.seniority,*p.skills]).strip()
def digest(p): return hashlib.sha256(json.dumps(p.model_dump(exclude={'external_id'}),sort_keys=True).encode()).hexdigest()
def fixture_embed(text):
    # An explicitly non-semantic deterministic test embedding; never marketed as transformer inference.
    result=[0.0]*64
    for word in tokens(text): result[int(hashlib.sha256(word.encode()).hexdigest()[:8],16)%64]+=1
    norm=math.sqrt(sum(x*x for x in result)) or 1
    return [x/norm for x in result]
class Embedder:
    def __init__(self,mode='fixture'):
        self.mode=mode;self.model=None;self.version='fixture-hash-v1'
        if mode=='sentence-transformers':
            from sentence_transformers import SentenceTransformer
            self.model=SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2',device='cpu')
            self.version='sentence-transformers/all-MiniLM-L6-v2'
    def encode(self,text): return self.model.encode(text,normalize_embeddings=True).tolist() if self.model else fixture_embed(text)
def rrf(rankings,k=60):
    result={}
    for ranking in rankings:
        for rank,identity in enumerate(ranking,1): result[identity]=result.get(identity,0)+1/(k+rank)
    return result
def preferences(job,skills,remote):
    overlap=len(set(skills)&set(job['skills']))/max(1,len(set(skills)))
    return {'skills':0.02*overlap,'remote':0.01*int(remote and job['remote'])}
def recall(ranked,relevant,k): return len(set(ranked[:k])&set(relevant))/len(set(relevant)) if relevant else 0.0
def ndcg(ranked,relevant,k=10):
    dcg=sum(1/math.log2(i+2) for i,x in enumerate(ranked[:k]) if x in relevant)
    ideal=sum(1/math.log2(i+2) for i in range(min(k,len(relevant))))
    return dcg/ideal if ideal else 0.0
