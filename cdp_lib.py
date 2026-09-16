
import socket, base64, os, json, struct, urllib.request, sys, time
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
def rf(s,n):
    buf=b''
    while len(buf)<n:
        c=s.recv(n-len(buf))
        if not c: raise Exception('closed')
        buf+=c
    return buf
def ws_port(port):
    j=json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=8).read())
    page=[t for t in j if t.get('type')=='page'][0]
    hp=page['webSocketDebuggerUrl'].split('/')[2].split(':')
    s=socket.create_connection((hp[0],int(hp[1])),timeout=8)
    path=page['webSocketDebuggerUrl'].split(':'+hp[1],1)[1]
    key=base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {path} HTTP/1.1\r\nHost: {hp[0]}:{hp[1]}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    resp=b''
    while b'\r\n\r\n' not in resp: resp+=s.recv(4096)
    M=[0]
    def send(method, params):
        M[0]+=1
        d=json.dumps({'id':M[0],'method':method,'params':params}).encode('utf-8')
        L=len(d); m=os.urandom(4)
        if L<126: hh=struct.pack('!BB',0x81,0x80|L)
        elif L<65536: hh=struct.pack('!BBH',0x81,0x80|126,L)
        else: hh=struct.pack('!BBQ',0x81,0x80|127,L)
        s.sendall(hh+m+bytes(b^m[i%4] for i,b in enumerate(d)))
    def recv():
        while True:
            f1=rf(s,1)[0]; f2=rf(s,1)[0]
            op=f1&0x0f; L=f2&0x7f
            if L==126: L=struct.unpack('!H',rf(s,2))[0]
            elif L==127: L=struct.unpack('!Q',rf(s,8))[0]
            d=rf(s,L)
            if op==9: continue
            return json.loads(d.decode('utf-8','replace'))
    def call(method, params):
        send(method, params)
        for _ in range(80):
            m=recv()
            if m.get('id')==M[0]: return m
        return {}
    call._s=s
    return call

def ev(call, expr, await_p=False):
    r=call('Runtime.evaluate', {'expression':expr, 'returnByValue':True, 'awaitPromise':await_p})
    v=((r.get('result') or {}).get('result') or {}).get('value')
    if isinstance(v,str) and v and v[0] in '{[':
        try: return json.loads(v)
        except Exception: return v
    return v

def rect_pred(call, pred):
    expr=f"(()=>{{const b=[...document.querySelectorAll('button,[role=button]')].find(x=>{pred});if(!b)return 'null';const rr=b.getBoundingClientRect();return JSON.stringify({{x:rr.x+rr.width/2,y:rr.y+rr.height/2}});}})()"
    r=call('Runtime.evaluate', {'expression':expr, 'returnByValue':True})
    v=((r.get('result') or {}).get('result') or {}).get('value')
    try: return json.loads(v) if v else None
    except Exception: return None
