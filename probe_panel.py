
import socket, base64, os, json, struct, urllib.request, sys
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
def rf(s,n):
    buf=b''
    while len(buf)<n:
        c=s.recv(n-len(buf))
        if not c: raise Exception('closed')
        buf+=c
    return buf
def ws(url, expr):
    port = None; host='127.0.0.1'
    nxt = json.loads(urllib.request.urlopen(url, timeout=8).read())
    page=[t for t in nxt if t.get('type')=='page'][0]
    hp=page['webSocketDebuggerUrl'].split('/')[2].split(':')
    s=socket.create_connection((hp[0],int(hp[1])),timeout=8)
    path=page['webSocketDebuggerUrl'].split(':'+hp[1],1)[1]
    key=base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {path} HTTP/1.1\r\nHost: {hp[0]}:{hp[1]}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    resp=b''
    while b'\r\n\r\n' not in resp: resp+=s.recv(4096)
    def rf(n):
        buf=b''
        while len(buf)<n:
            c=s.recv(n-len(buf))
            if not c: raise Exception('closed')
            buf+=c
        return buf
    def send(p):
        d=p.encode('utf-8'); L=len(d); m=os.urandom(4)
        if L<126: hh=struct.pack('!BB',0x81,0x80|L)
        elif L<65536: hh=struct.pack('!BBH',0x81,0x80|126,L)
        else: hh=struct.pack('!BBQ',0x81,0x80|127,L)
        s.sendall(hh+m+bytes(b^m[i%4] for i,b in enumerate(d)))
    def recv():
        while True:
            f1=rf(1)[0]; f2=rf(1)[0]
            op=f1&0x0f; L=f2&0x7f
            if L==126: L=struct.unpack('!H',rf(2))[0]
            elif L==127: L=struct.unpack('!Q',rf(8))[0]
            d=rf(L)
            if op==9: continue
            return d.decode('utf-8','replace')
    send(json.dumps({'id':1,'method':'Runtime.evaluate','params':{'expression':expr,'returnByValue':True}}))
    for _ in range(30):
        msg=json.loads(recv())
        if msg.get('id')==1: return (msg.get('result') or {}).get('result',{}).get('value')
EX = """
(() => {
  const p=document.querySelector('[class*=panels]')||{textContent:''};
  return JSON.stringify({panel:p.textContent.slice(0,80)});
})()
"""
for port in (9223,9224,9225):
    print(port, ws(f'http://127.0.0.1:{port}/json', EX))
