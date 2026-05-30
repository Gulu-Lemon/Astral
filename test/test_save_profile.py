"""Test profile save with whitespace"""
import sys,os,json,urllib.request,threading,time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from server import app
threading.Thread(target=lambda:app.run(host='127.0.0.1',port=18012,debug=False,threaded=True),daemon=True).start()
time.sleep(3)
base = 'http://127.0.0.1:18012'

# Test with whitespace in values
req=urllib.request.Request(base+'/api/profiles',
    data=json.dumps({'name':'TestProfile','base_url':' https://test.com ','api_key':' sk-xxx ','model':' deepseek '}).encode(),
    headers={'Content-Type':'application/json'})
resp = json.loads(urllib.request.urlopen(req).read())
print(f'Save result: ok={resp.get("ok")}')

# Read back
resp2 = json.loads(urllib.request.urlopen(base+'/api/profiles').read())
profiles = resp2.get('profiles', [])
print(f'Profiles count: {len(profiles)}')
for p in profiles:
    has_space = ' ' in p.get('base_url','') or p.get('base_url','').startswith(' ')
    print(f'  name=[{p.get("name")}] url=[{p.get("base_url")}] model=[{p.get("model")}] has_spaces={has_space}')

# Test activate
r = json.loads(urllib.request.urlopen(urllib.request.Request(
    base+'/api/profiles/activate', 
    data=json.dumps({'name':'TestProfile'}).encode(),
    headers={'Content-Type':'application/json'}
)).read())
print(f'Activate: ok={r.get("ok")}')

# Check LLM config after activate
resp3 = json.loads(urllib.request.urlopen(base+'/api/profiles').read())
print(f'Active: {resp3.get("active")}')

# Clean up
urllib.request.urlopen(urllib.request.Request(
    base+'/api/profiles/delete',
    data=json.dumps({'name':'TestProfile'}).encode(),
    headers={'Content-Type':'application/json'}
)).read()
print('Cleaned up')
