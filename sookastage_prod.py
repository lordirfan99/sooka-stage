
# SookaStage runner — production flow per streamer (v1 draft, main-flow)
# Usage: python sookastage_prod.py <port> <expected_browser_tile>  e.g. python sookastage_prod.py 9223 Brave
# Flow: deep-link nav (URL in config) -> ensure window foreground via ctypes -> join/continue-without-starting -> share -> tile -> Go Live.
# Author: Sportmania agent (2026-09-17)
import ctypes, ctypes.wintypes as wt, time, sys, json, socket, base64, os, struct, urllib.request
try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
except Exception: pass

pyautogui, pyautogui_FAILSAFE = None, None
def ensure_pyautogui():
    global pyautogui
    import pyautogui as _p
    _p.FAILSAFE=False
    return _p

LOG = r'C:\Users\irfan\sookastage_prod.log'
def log(m):
    import datetime as _dt
    try:
        import datetime as _dt
        with open(LOG,'a',encoding='utf-8',errors='replace') as f:
            f.write(str(_dt.datetime.now())[:22]+' '+str(m)+'\n')
    except Exception:
        pass

def rf(s,n):
    buf=b''
    while len(buf)<n: buf+=s.recv(n-len(buf))
    return buf

class CDP:
    def __init__(s, port):
        j=json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=8).read())
        page=[t for t in j if t.get('type')=='page' and t.get('url','').startswith('https://discord.com/channels/1251553669644816518')][0]
        url=page['webSocketDebuggerUrl']; hp=url.split('/')[2].split(':')
        s.s=socket.create_connection((hp[0],int(hp[1])),timeout=10)
        path=url.split(':'+hp[1],1)[1]
        key=base64.b64encode(os.urandom(16)).decode()
        s.s.sendall((f"GET {path} HTTP/1.1\r\nHost: {hp[0]}:{hp[1]}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        resp=b''
        while b'\r\n\r\n' not in resp: resp+=s.s.recv(4096)
        s.M=[0]
    def _send(s, m, p):
        s.M[0]+=1
        d=json.dumps({'id':s.M[0],'method':m,'params':p}).encode()
        L=len(d); mask=os.urandom(4)
        if L<126: hh=struct.pack('!BB',0x81,0x80|L)
        elif L<65536: hh=struct.pack('!BBH',0x81,0x80|126,L)
        else: hh=struct.pack('!BBQ',0x81,0x80|127,L)
        s.s.sendall(hh+mask+bytes(b^mask[i%4] for i,b in enumerate(d)))
    def _recv(s):
        b1=rf(s.s,2); L=b1[1]&0x7F
        if L==126: L=struct.unpack('!H', rf(s.s,2))[0]
        elif L==127: L=struct.unpack('!Q', rf(s.s,8))[0]
        d=rf(s.s,L)
        return json.loads(d.decode('utf-8','replace'))
    def call(s, m, p={}, tries=60):
        s._send(m,p)
        for _ in range(tries):
            r=s._recv()
            if r.get('id')==s.M[0]: return r
        return {}
    def ev(s, expr):
        r=s.call('Runtime.evaluate', {'expression':expr, 'returnByValue':True})
        v=((r.get('result') or {}).get('result') or {}).get('value')
        if isinstance(v,str) and v[:1] in ('{','['):
            try: return json.loads(v)
            except Exception: return v
        return v
    def clipped_click(s, pred):
        """1 rect lookup + real CDP Input.dispatchMouseEvent at rect; returns rect"""
        expr = "(()=>{const b=[...document.querySelectorAll('button,[role=button],a,li')].find(x=>"+pred+");if(!b)return null;const rr=b.getBoundingClientRect();return JSON.stringify({x:rr.x+rr.width/2,y:rr.y+rr.height/2});})()"
        v = s.ev(expr)
        d = None
        try: d = json.loads(v) if v else None
        except Exception: d = None
        log('rect '+repr(d))
        if not d: return None
        for t in ('mousePressed','mouseReleased'):
            s.call('Input.dispatchMouseEvent', {'type':t, 'x':d['x'], 'y':d['y'], 'button':'left', 'buttons':1, 'clickCount':1, 'pointerType':'mouse'})
            time.sleep(0.12)
        return d

def get_win_rect_by_pid(pid, min_w=400):
    u=ctypes.windll.user32
    CB=ctypes.WINFUNCTYPE(ctypes.c_bool, wt.HWND, wt.LPARAM)
    res=[]
    def cb(h,l):
        rr=wt.RECT(); u.GetWindowRect(h,ctypes.byref(rr))
        wp=wt.DWORD(); u.GetWindowThreadProcessId(h,ctypes.byref(wp))
        if wp.value==pid:
            buf=ctypes.create_unicode_buffer(128); u.GetWindowTextW(h,buf,128)
            res.append((h,rr.left,rr.top,buf.value,rr.right-rr.left,u.IsIconic(h)))
        return True
    u.EnumWindows(CB(cb),0)
    big=[t for t in res if 'Discord' in t[3] and t[4]>=min_w]
    if big: return big[0]
    # fallback by biggest window
    res.sort(key=lambda t:-t[4])
    return res[0] if res else None

def main():
    if len(sys.argv)<3: print('usage: sookastage_prod.py <port> <browser>'); return
    port=sys.argv[1]; browser=sys.argv[2]
    u=ctypes.windll.user32
    import subprocess as _sp
    out=_sp.check_output(f'netstat -ano | findstr ":{port}"', shell=True).decode(errors='replace')
    pid=None
    for line in out.splitlines():
        if 'LISTENING' in line: pid=int(line.split()[-1])
    log(f'pid {pid}')
    win=get_win_rect_by_pid(pid); h,x,y,title,w,ic=win
    if ic: u.ShowWindow(h,9); time.sleep(1.2)
    u.SetForegroundWindow(h); time.sleep(1.8)
    rr=wt.RECT(); u.GetWindowRect(h,ctypes.byref(rr)); x,y=rr.left,rr.top
    log('origin '+repr((x,y,w)))
    cdp=CDP(port)
    # 1 continue-without-starting if waiting-lobby cards are visible
    cdp.clipped_click("x.textContent.includes('Continue without starting')")
    time.sleep(8)
    # 2 share button via actual rect
    cdp.clipped_click("((x.getAttribute('aria-label')||'')+' '+(x.textContent||'')).includes('Share Your Screen')")
    time.sleep(12)
    # 3 tile matching target browser
    cdp.clipped_click("(()=>{const dlg=document.querySelector('[role=dialog]');if(!dlg)return false;const els=[...dlg.querySelectorAll('button,[role=button]')].filter(e=>{const t=((e.getAttribute('aria-label')||'')+' '+(e.textContent||'')).toLowerCase();return t.includes('share screen')&&t.includes('"+browser.lower()+"')&&!t.includes('discord');});return els.length>0;})()")
    time.sleep(7)
    # 3 golive
    cdp.clipped_click("(()=>{const dlg=document.querySelector('[role=dialog]');if(!dlg)return false;const b=[...dlg.querySelectorAll('button')].find(b=>/go live/i.test(b.textContent));return !!b;})()")
    time.sleep(7)
    cdp.clipped_click("(()=>{const dlg=document.querySelector('[role=dialog]');if(!dlg)return false;const b=[...dlg.querySelectorAll('button')].find(b=>/go live/i.test(b.textContent));return !!b;})()")
    time.sleep(6)
    st=cdp.ev("(()=>{const b=document.body.innerText||'';return JSON.stringify({stop:b.includes('Stop Streaming'), sooka:b.includes('Watch online Live Sports')});})()")
    log('state '+repr(st))
    try: cdp.s.close()
    except Exception: pass
    print('done', st)

if __name__ == '__main__':
    main()
