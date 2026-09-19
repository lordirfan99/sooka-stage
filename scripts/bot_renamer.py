# -*- coding: utf-8 -*-
"""SportMania Bot renamer — VPS-hosted, 24/7 stage + channel name manager.

Replaces the PC's voice_renamer.py with a bot-token-only system. Pulls the
match allocation from Sooka Manager (ngrok tunnel on the PC) and pushes
stage topics + channel names via the SPORTMANIA BOT. Works even when the PC
Discord clients are offline. Log: /home/ubuntu/sooka-stage/renamer.log
"""
import json
import os
import time
import urllib.request
import urllib.error

GUILD = '1251553669644816518'
STAGE_CHANNELS = {
    1: '1477692113738137600',
    2: '1481358977584599283',
    3: '1481359453759475876',
}

NGROK_FILE = '/home/ubuntu/sooka-stage/ngrok_url.txt'
if os.path.exists(NGROK_FILE):
    raw = open(NGROK_FILE).read().strip()
    SOOKA_API = raw.replace('/dashboard', '').rstrip('/')
else:
    SOOKA_API = 'http://127.0.0.1:8080'
if 'ngrok-free' not in SOOKA_API:
    SOOKA_API = 'https://chowder-hypocrisy-democrat.ngrok-free.dev'

LOOP_DELAY = 15
LOG_PATH = '/home/ubuntu/sooka-stage/renamer.log'
SOOKA_TIMEOUT = 12
H_SOOKA = {'User-Agent': 'SookaStageBot/1.0', 'ngrok-skip-browser-warning': '1'}

BOT_TOKEN = None
for line in open('/home/ubuntu/.hermes/.env'):
    s = line.strip()
    if s.startswith('#') or '=' not in s:
        continue
    k, v = s.split('=', 1)
    if k == 'DISCORD_BOT_TOKEN':
        BOT_TOKEN = v.strip()
        break
if not BOT_TOKEN:
    raise FileNotFoundError('DISCORD_BOT_TOKEN not found in ~/.hermes/.env')

H = {'Authorization': 'Bot ' + BOT_TOKEN,
     'User-Agent': 'DiscordBot (https://sportmania.my, 1.0)',
     'Content-Type': 'application/json'}


def log(line):
    with open(LOG_PATH, 'a', encoding='utf-8') as f:
        f.write('[%s] %s\n' % (time.strftime('%Y-%m-%d %H:%M:%S'), line))


def api_patch_stage(cid, topic):
    data = json.dumps({'topic': topic}).encode()
    req = urllib.request.Request(
        'https://discord.com/api/v9/stage-instances/%s' % cid,
        headers=H, data=data)
    req.get_method = lambda: 'PATCH'
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or b'{}')


def api_patch_channel_name(cid, name):
    data = json.dumps({'name': name}).encode()
    req = urllib.request.Request(
        'https://discord.com/api/v9/channels/%s' % cid,
        headers=H, data=data)
    req.get_method = lambda: 'PATCH'
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or b'{}')


def fetch_allocation():
    url = SOOKA_API + '/sooka-dashboard.json'
    req = urllib.request.Request(url, headers=H_SOOKA)
    with urllib.request.urlopen(req, timeout=SOOKA_TIMEOUT) as r:
        return json.loads(r.read())


def topic_string(stream, match):
    title = match.get('title') or 'Idle'
    if not title.startswith('(L)') and match.get('is_live'):
        title = '(L) ' + title
    return 'Stream %d — %s' % (stream, title)


def name_string(match):
    title = (match.get('title') or 'Idle').replace('(L) ', '')
    return (title.replace('(L) ', '').replace('(L)','')[:32]).strip() or 'Idle'


def sync_tick():
    payload = fetch_allocation()
    if not payload:
        log('no allocation (sooka API unreachable)')
        return
    allocation = payload.get('allocation') or []
    for slot in allocation:
        sid = slot.get('stream')
        match = slot.get('match') or {}
        try:
            stream = int(str(sid).lstrip('sS'))
        except ValueError:
            continue
        cid = STAGE_CHANNELS.get(stream)
        if not cid:
            continue
        topic = topic_string(stream, match)
        name = name_string(match)
        try:
            api_patch_stage(cid, topic)
            log('topic[%d] -> %s' % (stream, topic[:60]))
        except Exception as e:
            log('topic[%d] ERR %s' % (stream, str(e)[:80]))
        time.sleep(1.2)
        try:
            api_patch_channel_name(cid, name)
            log('name[%d] -> %s' % (stream, name[:60]))
        except Exception as e:
            log('name[%d] ERR %s' % (stream, str(e)[:80]))


def main():
    log('=== Bot renamer started (VPS-paced, no PC dep) ===')
    while True:
        try:
            sync_tick()
        except Exception as e:
            log('tick err ' + str(e)[:120])
        time.sleep(LOOP_DELAY)


if __name__ == '__main__':
    main()
