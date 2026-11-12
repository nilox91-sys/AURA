"""Download pinned official assets and rebuild AURA's rig preferences."""
import argparse,hashlib,json,os,tempfile,urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
HOSTS={'raw.githubusercontent.com','cubism.live2d.com','cdn.jsdelivr.net','www.live2d.com'}

def destination(root,path):
    target=(root/path).resolve()
    if not target.is_relative_to(root.resolve()):raise ValueError('Asset path outside project')
    return target

def matches(path,entry):
    return path.is_file() and path.stat().st_size==entry['bytes'] and hashlib.sha256(path.read_bytes()).hexdigest()==entry['sha256']

def atomic_write(path,content):
    path.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent,delete=False) as stream:
        stream.write(content);temporary=stream.name
    try:os.replace(temporary,path)
    finally:
        if os.path.exists(temporary):os.unlink(temporary)

def materialize(root):
    expressions=json.loads((root/'avatar-expressions.json').read_text(encoding='utf-8'))
    for filename,content in expressions.items():
        atomic_write(destination(root,'static/models/hiyori/expressions/'+filename),content.replace('\n','\r\n').encode('utf-8'))
    for model in ('Haru','Hiyori'):
        folder=root/'static/models'/model.lower()
        data=json.loads((folder/(model+'.source.model3.json')).read_text(encoding='utf-8'))
        for motions in data['FileReferences']['Motions'].values():
            for motion in motions:motion.pop('Sound',None)
        if model=='Hiyori':data['FileReferences']['Expressions']=[{'Name':name,'File':'expressions/'+name+'.exp3.json'} for name in ('cozy-happy','cozy-sad','cozy-alert','cozy-surprised')]
        atomic_write(folder/(model+'.model3.json'),json.dumps(data,indent=2).replace('\n','\r\n').encode('utf-8'))

def prepare(root=ROOT,check=False):
    manifest=json.loads((root/'asset-manifest.json').read_text(encoding='utf-8'))
    generated={'static/models/'+name.lower()+'/'+name+'.model3.json' for name in ('Haru','Hiyori')}
    generated.update('static/models/hiyori/expressions/'+name for name in json.loads((root/'avatar-expressions.json').read_text(encoding='utf-8')))
    def fetch(entry):
        path=destination(root,entry['path'])
        if matches(path,entry) or entry['path'] in generated or check:return
        parsed=urlsplit(entry['url'])
        if parsed.scheme!='https' or parsed.hostname not in HOSTS:raise ValueError('Source not permitted: '+entry['path'])
        req=urllib.request.Request(entry['url'],headers={'User-Agent':'AURA-avatar-setup/2.0'})
        with urllib.request.urlopen(req,timeout=30) as response:
            if urlsplit(response.url).hostname not in HOSTS:raise ValueError('Unexpected download destination')
            content=response.read(min(entry['bytes']+1,24*1024*1024))
        if len(content)!=entry['bytes'] or hashlib.sha256(content).hexdigest()!=entry['sha256']:
            raise ValueError('La sorgente è cambiata; nessun sostituto installato: '+entry['path'])
        atomic_write(path,content)
    with ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(fetch,manifest))
    if not check:materialize(root)
    missing=[item['path'] for item in manifest if not matches(destination(root,item['path']),item)]
    if missing:raise RuntimeError('Asset mancanti o differenti: '+', '.join(missing))
    print(f'Avatar verificati: {len(manifest)} file. Nessuna chiave API richiesta.')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Scarica i modelli ufficiali Live2D. Termini e fonti: licenses/THIRD_PARTY.md')
    parser.add_argument('--check',action='store_true',help='Verifica senza scaricare o modificare file')
    args=parser.parse_args()
    try:prepare(check=args.check)
    except Exception as error:parser.exit(1,str(error)+'\n')
