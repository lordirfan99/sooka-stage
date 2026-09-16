
import ctypes, ctypes.wintypes as wt, time, sys, pyautogui, subprocess, json, socket, base64, os, struct, urllib.request
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
pyautogui.FAILSAFE=False
u=ctypes.windll.user32
LOG=r'C:\Users\irfan\m40.log'
def L(m):
    open(LOG,'a',encoding='utf-8',errors='replace').write(str(m)+'\n')
def rf(s,n):
    b=b''
    while len(b)<n: b+=s.recv(n-len(b))
    return b
def ws_conn(port):
    j=json.loads(urllib.request.urlopen(f'http://127.0.0.1:{port}/json',timeout=8).read())
    page=[t for t in j if t.get('type')=='page'][0]
    url=page['webSocketDebuggerUrl']; hp=url.split('/')[2].split(':')
    s=socket.create_connection((hp[0],int(hp[1])),timeout=8)
    path=url.split(':'+hp[1],1)[1]
    key=base64.b64encode(os.urandom(16)).decode()
    s.sendall((f"GET {path} HTTP/1.1\r\nHost: {hp[0]}:{hp[1]}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
    resp=b''
    while b'\r\n\r\n' not in resp: resp+=s.recv(4096)
    M=[0]
    def send(m,p={}):
        M[0]+=1
        d=json.dumps({'id':M[0],'method':m,'params':p}).encode()
        L=len(d); m=os.urandom(4)
        if L<126: h=struct.pack('!BB',0x81,0x80|L)
        elif L<65536: h=struct.pack('!BBH',0x81,0x80|126,L)
        else: h=struct.pack('!BBQ',0x81,0x80|127,L)
        s.sendall(h+m+bytes(b^m[i%4] for i,b in enumerate(d)))
    def recv():
        b1=rf(s,2); L=b1[1]&0x7F
        if L==126: L=struct.unpack('!H', rf(s,2))[0]
        elif L==127: L=struct.unpack('!Q', rf(s,8))[0]
        d=rf(s,L)
        return json.loads(d.decode('utf-8','replace'))
    def call(m,p={}):
        send(m,p)
        for _ in range(60):
            r=recv()
            if r.get('id')==M[0]: return r
    call._s=s
    return call
try:
    out=subprocess.check_output('netstat -ano | findstr ":9223"', shell=True).decode(errors='replace')
    pid=None
    for line in out.splitlines():
        if 'LISTENING' in line: pid=int(line.split()[-1])
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
    big=[t for t in res if 'Discord' in t[3]]
    h,x,y,title,w,ic=big[0]
    if ic:
        u.ShowWindow(h,9); time.sleep(1.2)
    u.SetForegroundWindow(h); time.sleep(1.8)
    rr=wt.RECT(); u.GetWindowRect(h,ctypes.byref(rr))
    x,y=rr.left,rr.top; L('origin '+repr((x,y,w)))
    def cl(px,py,label,sleep=6):
        pyautogui.moveTo(x+px,y+py,duration=0.25)
        pyautogui.click(x+px,y+py); time.sleep(sleep); L(label)
    call=ws_conn(9223)
    call('Page.navigate', {'url':'https://discord.com/channels/1251553669644816518/1477692113738137600'})
    L('deep-nav'); time.sleep(16)
    try: call._s.close()
    except Exception: pass
    cl(677,470,'continue',14)
    cl(620,486,'share',20)
    cl(250,245,'tile1',9)
    cl(487,512,'golive',7)
    cl(487,512,'golive2',5)
    pyautogui.screenshot(region=(x,y,976,528)).save(r'C:\Users\irfan\m40.png')
    L('shot')
    print('ok')
except Exception as e:
    L('FATAL '+repr(e)[:200])
    print('fail')
