# -*- coding: utf-8 -*-
"""
MMH CONTROL — موقع تحكم في البوت (ملف واحد) للرفع على Vercel من GitHub.
- سمّي الملف app.py وارفعه على GitHub لوحده (مفيش حاجة تانية مطلوبة).
- في Vercel > Settings > Environment Variables ضيف:  DISCORD_TOKEN = توكن البوت
  (اختياري) DASH_PASSWORD لتغيير الباسورد — الافتراضي 997816
- البوت نفسه يفضل شغال مكانه؛ الموقع بيكلّم Discord مباشرة بنفس التوكن.
"""
import hashlib, hmac, json, os, time, urllib.error, urllib.request
from datetime import datetime, timedelta, timezone

TOKEN = os.environ.get("DISCORD_TOKEN", "")
PASSWORD = os.environ.get("DASH_PASSWORD", "997816")
SECRET = (TOKEN or "mmh") + PASSWORD
API = "https://discord.com/api/v10"


def dc(method, path, body=None):
    if not TOKEN:
        raise ValueError("DISCORD_TOKEN مش متظبط في Vercel")
    req = urllib.request.Request(API + path, method=method, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Authorization": "Bot " + TOKEN, "Content-Type": "application/json",
                                          "User-Agent": "DiscordBot (https://mmh.panel, 1.0)"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("message", "")
        except Exception:
            msg = ""
        raise ValueError(f"Discord ({e.code}): {msg or 'فشل الطلب'} — راجع صلاحيات البوت")


def sign(exp):
    return f"{exp}.{hmac.new(SECRET.encode(), str(exp).encode(), hashlib.sha256).hexdigest()}"


def valid(tok):
    try:
        exp, _ = tok.split(".")
        return int(exp) > time.time() and hmac.compare_digest(sign(exp), tok)
    except Exception:
        return False


def h_state(d):
    me = dc("GET", "/users/@me")
    gs = dc("GET", "/users/@me/guilds")
    return {"bot": me.get("username", "bot"), "guilds": [{"id": g["id"], "name": g["name"], "icon": g.get("icon")} for g in gs]}


def h_channels(d):
    ch = dc("GET", f"/guilds/{int(d['guild'])}/channels")
    ch = sorted((c for c in ch if c["type"] in (0, 5)), key=lambda c: c.get("position", 0))
    return {"channels": [[c["id"], c["name"]] for c in ch]}


def h_send(d):
    text = d["text"][:4000]
    body = {"allowed_mentions": {"parse": ["users", "roles"] + (["everyone"] if d.get("everyone") else [])}}
    if d.get("embed"):
        body["embeds"] = [{"title": (d.get("title") or "")[:250], "description": text,
                           "color": int((d.get("color") or "#9b59ff").lstrip("#"), 16),
                           "footer": {"text": "✦ Powered by MMH ✦"}}]
        if d.get("everyone"):
            body["content"] = "@everyone"
    else:
        body["content"] = text[:2000]
    if d.get("reply"):
        body["message_reference"] = {"message_id": str(int(d["reply"]))}
    dc("POST", f"/channels/{int(d['channel'])}/messages", body)
    return {"ok": 1}


def h_messages(d):
    out = []
    for m in dc("GET", f"/channels/{int(d['channel'])}/messages?limit=25"):
        out.append({"id": m["id"], "author": m["author"]["username"], "bot": m["author"].get("bot", False),
                    "content": m.get("content", "")[:500], "time": m["timestamp"][:19].replace("T", " ")})
    return {"messages": out}


def h_delete(d):
    dc("DELETE", f"/channels/{int(d['channel'])}/messages/{int(d['id'])}")
    return {"ok": 1}


def h_mod(d):
    g, u, a = int(d["guild"]), int(d["user"]), d["action"]
    if a == "timeout":
        until = (datetime.now(timezone.utc) + timedelta(minutes=max(1, min(int(d["minutes"]), 40320)))).isoformat()
        dc("PATCH", f"/guilds/{g}/members/{u}", {"communication_disabled_until": until})
    elif a == "untimeout":
        dc("PATCH", f"/guilds/{g}/members/{u}", {"communication_disabled_until": None})
    elif a == "kick":
        dc("DELETE", f"/guilds/{g}/members/{u}")
    elif a == "ban":
        dc("PUT", f"/guilds/{g}/bans/{u}", {})
    elif a == "unban":
        dc("DELETE", f"/guilds/{g}/bans/{u}")
    else:
        raise ValueError("إجراء غلط")
    return {"ok": 1}


ROUTES = {"state": h_state, "channels": h_channels, "send": h_send, "messages": h_messages, "delete": h_delete, "mod": h_mod}


def process(method, path, token, raw):
    J = "application/json; charset=utf-8"
    path = (path or "/").split("?")[0]
    if method != "POST" or not path.startswith("/api/"):
        return 200, "text/html; charset=utf-8", PAGE.encode("utf-8")

    def js(code, obj):
        return code, J, json.dumps(obj, ensure_ascii=False).encode("utf-8")

    name = path[5:].strip("/")
    try:
        d = json.loads(raw or b"{}")
        if name == "login":
            time.sleep(0.8)
            if hmac.compare_digest(str(d.get("password", "")).encode(), PASSWORD.encode()):
                return js(200, {"token": sign(int(time.time()) + 86400)})
            return js(403, {"error": "الباسورد غلط"})
        if not valid(token or "") or name not in ROUTES:
            return js(401, {"error": "unauthorized"})
        return js(200, ROUTES[name](d))
    except Exception as ex:
        return js(400, {"error": str(ex)[:250] or "خطأ"})


from http.server import BaseHTTPRequestHandler


class handler(BaseHTTPRequestHandler):
    def _go(self, method):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        code, ctype, body = process(method, self.path, self.headers.get("X-Token"), raw)
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self._go("GET")

    def do_POST(self):
        self._go("POST")

    def log_message(self, *a):
        pass


PAGE = r'''<!DOCTYPE html><html lang="ar" dir="rtl"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>MMH Control</title><link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>👑</text></svg>">
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700;900&display=swap" rel="stylesheet">
<style>
:root{--p:#9b59ff;--c:#1db9ff;--k:#ff3b9a;--bg:#07060f;--g:rgba(255,255,255,.055);--b:rgba(255,255,255,.1);--t:#f2eefc;--m:#9a93b8}
*{box-sizing:border-box;margin:0;font-family:Tajawal,system-ui,sans-serif}
body{background:var(--bg);color:var(--t);min-height:100vh;overflow-x:hidden}
#bg{position:fixed;inset:0;z-index:0}
.blob{position:fixed;border-radius:50%;filter:blur(90px);opacity:.35;z-index:0;animation:fl 14s ease-in-out infinite alternate}
.b1{width:480px;height:480px;background:var(--p);top:-120px;right:-80px}.b2{width:420px;height:420px;background:var(--c);bottom:-120px;left:-80px;animation-delay:-5s}.b3{width:300px;height:300px;background:var(--k);top:40%;left:40%;opacity:.18;animation-delay:-9s}
@keyframes fl{to{transform:translate(60px,-50px) scale(1.2)}}
@keyframes up{from{opacity:0;transform:translateY(26px) scale(.97)}to{opacity:1;transform:none}}
@keyframes spin{to{transform:rotate(360deg)}}@keyframes shake{25%,75%{transform:translateX(-10px)}50%{transform:translateX(10px)}}
@keyframes pulse{0%{box-shadow:0 0 0 0 #2ecc71aa}100%{box-shadow:0 0 0 12px #2ecc7100}}
@keyframes eq{0%,100%{height:6px}50%{height:34px}}@keyframes sh{to{background-position:200% 0}}
.logo{font-weight:900;font-size:2.2rem;background:linear-gradient(90deg,var(--p),var(--c),var(--k),var(--p));background-size:200% 100%;-webkit-background-clip:text;color:transparent;animation:sh 4s linear infinite}
#login{position:fixed;inset:0;z-index:20;display:grid;place-items:center;transition:.7s}#login.out{opacity:0;transform:scale(1.15);pointer-events:none}
.lc{width:min(400px,90vw);padding:40px 32px;text-align:center;border-radius:28px;background:var(--g);border:1px solid var(--b);backdrop-filter:blur(24px);animation:up .9s both;position:relative}
.lc:before,.card:before{content:"";position:absolute;inset:-1px;border-radius:inherit;padding:1px;background:conic-gradient(from var(--a,0deg),transparent 60%,var(--p),var(--c),transparent);-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask-composite:exclude;animation:rot 5s linear infinite;pointer-events:none}
@property --a{syntax:"<angle>";inherits:false;initial-value:0deg}@keyframes rot{to{--a:360deg}}
.crown{font-size:3.4rem;display:block;animation:fl 3s ease-in-out infinite alternate;filter:drop-shadow(0 0 18px var(--p))}
input,select,textarea{width:100%;padding:13px 16px;border-radius:14px;border:1px solid var(--b);background:#0003;color:var(--t);font-size:1rem;outline:0;transition:.25s}
input:focus,select:focus,textarea:focus{border-color:var(--p);box-shadow:0 0 0 4px #9b59ff30}select option{background:#14112a}
.btn{padding:12px 20px;border:0;border-radius:14px;cursor:pointer;font-weight:700;font-size:.95rem;color:#fff;background:linear-gradient(135deg,var(--p),var(--c));transition:.25s;position:relative;overflow:hidden}
.btn:hover{transform:translateY(-3px);box-shadow:0 10px 30px #9b59ff55}.btn:active{transform:scale(.95)}
.btn.s{background:var(--g);border:1px solid var(--b)}.btn.r{background:linear-gradient(135deg,#ff3b5c,#ff7a3b)}
#app{display:none;position:relative;z-index:2;min-height:100vh}#app.on{display:flex}
aside{width:250px;padding:22px 16px;position:sticky;top:0;height:100vh;border-left:1px solid var(--b);background:#0a081655;backdrop-filter:blur(20px);display:flex;flex-direction:column;gap:6px;animation:up .8s both}
aside .logo{font-size:1.7rem;text-align:center;margin-bottom:14px}
.nv{padding:13px 16px;border-radius:14px;cursor:pointer;color:var(--m);transition:.3s;font-weight:700;display:flex;gap:10px;border:1px solid transparent}
.nv:hover{background:var(--g);color:var(--t);transform:translateX(-6px)}.nv.on{background:linear-gradient(135deg,#9b59ff33,#1db9ff22);color:#fff;border-color:var(--b);box-shadow:0 0 24px #9b59ff22}
main{flex:1;padding:26px;max-width:1100px;margin:auto;min-width:0}
.top{display:flex;gap:14px;align-items:center;margin-bottom:22px;flex-wrap:wrap;animation:up .6s both}.top select{max-width:260px}
.dot{width:12px;height:12px;border-radius:50%;background:#2ecc71;animation:pulse 1.6s infinite}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:16px;margin-bottom:16px}
.card{position:relative;padding:22px;border-radius:22px;background:var(--g);border:1px solid var(--b);backdrop-filter:blur(18px);animation:up .7s both;animation-delay:calc(var(--i,0)*.08s);transition:transform .3s}
.card:hover{transform:translateY(-4px)}.card h3{margin-bottom:14px;font-size:1.1rem}
.num{font-size:2.6rem;font-weight:900;background:linear-gradient(135deg,#fff,var(--c));-webkit-background-clip:text;color:transparent}.lbl{color:var(--m)}
section{display:none}section.on{display:block;animation:up .5s both}
.row{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin-bottom:12px}.row>*{flex:1}.row .btn{flex:none}
.sw{width:54px;height:30px;border-radius:30px;background:#ffffff22;position:relative;cursor:pointer;transition:.3s;flex:none!important}.sw:after{content:"";position:absolute;top:3px;right:3px;width:24px;height:24px;border-radius:50%;background:#fff;transition:.3s}
.sw.on{background:linear-gradient(135deg,var(--p),var(--c));box-shadow:0 0 18px #9b59ff88}.sw.on:after{right:27px}
.tg{display:flex;justify-content:space-between;align-items:center;padding:13px 0;border-bottom:1px solid var(--b);gap:12px}.tg:last-child{border:0}.tg small{color:var(--m);display:block}
.np{display:flex;gap:18px;align-items:center}.np img{width:110px;height:110px;border-radius:18px;object-fit:cover;background:#0004;box-shadow:0 10px 40px #9b59ff44}
.eqw{display:flex;gap:4px;align-items:flex-end;height:36px}.eqw i{width:6px;height:6px;border-radius:3px;background:linear-gradient(var(--c),var(--p))}.eqw.pl i{animation:eq 1s ease-in-out infinite}.eqw.pl i:nth-child(2){animation-delay:.2s}.eqw.pl i:nth-child(3){animation-delay:.4s}.eqw.pl i:nth-child(4){animation-delay:.1s}.eqw.pl i:nth-child(5){animation-delay:.3s}
input[type=range]{padding:0;accent-color:var(--p);height:8px}
.chips{display:flex;flex-wrap:wrap;gap:8px;max-height:230px;overflow:auto}.chip{padding:6px 12px;border-radius:30px;background:#ff3b5c22;border:1px solid #ff3b5c55;cursor:pointer;font-size:.9rem;transition:.2s;direction:ltr}.chip:hover{background:#ff3b5c66;transform:scale(1.08)}
.log{max-height:520px;overflow:auto;display:flex;flex-direction:column;gap:8px}.lg{padding:12px 14px;border-radius:14px;background:#0003;border-right:3px solid var(--p);font-size:.88rem;animation:up .4s both}.lg b{color:var(--c)}.lg small{color:var(--m);display:block;margin-top:3px}
.q div{padding:8px 12px;border-radius:10px;background:#0003;margin-bottom:6px;font-size:.9rem}
#toast{position:fixed;bottom:24px;left:50%;transform:translateX(-50%);z-index:50;display:flex;flex-direction:column;gap:8px;align-items:center}
.ts{padding:12px 22px;border-radius:30px;background:#14112aee;border:1px solid var(--p);animation:up .4s both;box-shadow:0 10px 40px #0008}.ts.e{border-color:#ff3b5c}
@media(max-width:800px){aside{position:fixed;bottom:0;top:auto;height:auto;width:100%;flex-direction:row;overflow:auto;z-index:10;border:0;border-top:1px solid var(--b);padding:8px}aside .logo{display:none}.nv{white-space:nowrap;padding:10px 12px}main{padding:16px 14px 90px}#app{display:none}#app.on{display:block}}
.gi{width:44px;height:44px;border-radius:50%}textarea{resize:vertical}</style></head><body><canvas id="bg"></canvas><div class="blob b1"></div><div class="blob b2"></div><div class="blob b3"></div>
<div id="login"><div class="lc"><span class="crown">👑</span><div class="logo">MMH CONTROL</div><p class="lbl" style="margin:8px 0 22px">لوحة تحكم البوت — دخول خاص</p>
<input id="pw" type="password" placeholder="كلمة السر" inputmode="numeric" autocomplete="off"><button class="btn" id="go" style="width:100%;margin-top:14px">دخول ✦</button></div></div>
<div id="app"><aside><div class="logo">MMH</div>
<div class="nv on" data-t="home">🏠 نظرة عامة</div><div class="nv" data-t="send">✉️ إرسال رسالة</div><div class="nv" data-t="chat">💬 الشات المباشر</div><div class="nv" data-t="mod">🔨 الإدارة</div>
<div style="flex:1"></div><div class="nv" onclick="logout()">🚪 خروج</div></aside>
<main><div class="top"><span class="dot"></span><b id="bn" style="font-size:1.2rem">…</b><div style="flex:1"></div><select id="gs"></select><select id="tc"></select></div>

<section id="home" class="on"><div class="grid"><div class="card" style="--i:0"><div class="lbl">السيرفرات</div><div class="num" id="n1">0</div></div><div class="card" style="--i:1"><div class="lbl">البوت</div><div class="num" id="n2" style="font-size:1.6rem">—</div></div></div>
<div class="grid" id="gl"></div></section>

<section id="send"><div class="grid"><div class="card"><h3>✉️ اكتب الرسالة</h3>
<div class="row"><textarea id="sm" rows="7" placeholder="اكتب اللي عايز البوت يبعته في الروم المختارة…"></textarea></div>
<div class="tg"><div>إرسال كـ Embed فخم<small>بعنوان ولون</small></div><div class="sw" id="em"></div></div>
<div class="row" style="margin-top:10px"><input id="et" placeholder="عنوان الـ Embed"><input id="ec" type="color" value="#9b59ff" style="flex:none;width:64px;padding:4px;height:46px"></div>
<div class="tg"><div>السماح بمنشن @everyone</div><div class="sw" id="ev"></div></div>
<div class="row" style="margin-top:10px"><input id="rp" placeholder="ID رسالة للرد عليها (اختياري)"></div>
<button class="btn" id="sb" style="width:100%">🚀 ابعت دلوقتي</button></div>
<div class="card"><h3>👁️ معاينة</h3><div class="lg" id="pv" style="min-height:120px"><b>MMH</b><div id="pvt">الرسالة هتظهر هنا…</div></div></div></div></section>

<section id="chat"><div class="card"><h3>💬 آخر رسائل الروم (لايف)</h3><div class="log" id="ms"></div></div></section>

<section id="mod"><div class="card" style="max-width:520px"><h3>🔨 إجراء على عضو</h3>
<div class="row"><input id="mu" placeholder="ID العضو"></div>
<div class="row"><select id="ma"><option value="timeout">🔇 تايم أوت</option><option value="untimeout">🔊 فك التايم أوت</option><option value="kick">👢 طرد</option><option value="ban">🔨 بان</option><option value="unban">♻️ فك البان</option></select><input id="mm" type="number" value="10" min="1" placeholder="دقايق"></div>
<button class="btn r" id="mb" style="width:100%">تنفيذ</button></div></section>
</main></div><div id="toast"></div>
<script>
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
let TK=sessionStorage.getItem('tk')||'',tab='home',tm;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
async function api(n,d={}){const r=await fetch('/api/'+n,{method:'POST',headers:{'Content-Type':'application/json','X-Token':TK},body:JSON.stringify(d)});const j=await r.json().catch(()=>({error:'خطأ'}));if(r.status==401&&n!='login'){logout();throw 0}if(j.error)throw new Error(j.error);return j}
function toast(m,e){const t=document.createElement('div');t.className='ts'+(e?' e':'');t.textContent=m;$('#toast').append(t);setTimeout(()=>t.remove(),3200)}
async function act(n,d,m){try{const r=await api(n,d);toast(m||'تم ✓');return r}catch(e){e&&toast(e.message,1)}}
function logout(){sessionStorage.clear();location.reload()}
$('#go').onclick=async()=>{try{const r=await api('login',{password:$('#pw').value});TK=r.token;sessionStorage.setItem('tk',TK);enter()}catch(e){const c=$('.lc');c.style.animation='shake .4s';setTimeout(()=>c.style.animation='',500);toast(e&&e.message||'غلط',1)}};
$('#pw').onkeydown=e=>e.key=='Enter'&&$('#go').click();
function cnt(el,v){const t0=performance.now();(function f(t){const p=Math.min(1,(t-t0)/900);el.textContent=Math.round(v*(1-Math.pow(1-p,3)));p<1&&requestAnimationFrame(f)})(t0)}
async function enter(){$('#login').classList.add('out');$('#app').classList.add('on');try{const s=await api('state');$('#bn').textContent='✦ '+s.bot;cnt($('#n1'),s.guilds.length);$('#n2').textContent=s.bot;
$('#gs').innerHTML=s.guilds.map(g=>`<option value="${g.id}">${esc(g.name)}</option>`).join('');
$('#gl').innerHTML=s.guilds.map((g,i)=>`<div class="card" style="--i:${i}"><div class="row"><img class="gi" src="${g.icon?`https://cdn.discordapp.com/icons/${g.id}/${g.icon}.png?size=96`:'data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw=='}" style="flex:none"><b>${esc(g.name)}</b></div></div>`).join('');
await chans();tm=setInterval(()=>tab=='chat'&&msgs(),4000)}catch(e){e&&toast(e.message,1)}}
async function chans(){const r=await act('channels',{guild:$('#gs').value},'تم تحميل الرومات');if(r){$('#tc').innerHTML=r.channels.map(c=>`<option value="${c[0]}"># ${esc(c[1])}</option>`.replace('>#','>#')).join('');if(tab=='chat')msgs()}}
$('#gs').onchange=chans;$('#tc').onchange=()=>tab=='chat'&&msgs();
$$('.nv[data-t]').forEach(n=>n.onclick=()=>{tab=n.dataset.t;$$('.nv').forEach(x=>x.classList.remove('on'));n.classList.add('on');$$('section').forEach(s=>s.classList.toggle('on',s.id==tab));tab=='chat'&&msgs()});
$$('.sw').forEach(s=>s.onclick=()=>s.classList.toggle('on'));
$('#sm').oninput=$('#et').oninput=()=>{$('#pvt').textContent=$('#sm').value||'الرسالة هتظهر هنا…'};
$('#sb').onclick=async()=>{const t=$('#sm').value.trim();if(!t)return toast('اكتب رسالة',1);const b=$('#sb');b.disabled=1;
const r=await act('send',{channel:$('#tc').value,text:t,embed:$('#em').classList.contains('on'),title:$('#et').value,color:$('#ec').value,everyone:$('#ev').classList.contains('on'),reply:$('#rp').value.trim()},'اتبعتت 🚀');b.disabled=0;if(r){$('#sm').value='';$('#rp').value='';$('#pvt').textContent='الرسالة هتظهر هنا…'}};
async function msgs(){try{const r=await api('messages',{channel:$('#tc').value});$('#ms').innerHTML=r.messages.map(m=>`<div class="lg"><b>${esc(m.author)}${m.bot?' 🤖':''}</b><small>${esc(m.time)} — ${m.id}</small><div>${esc(m.content)||'<i>(مرفق/Embed)</i>'}</div><div class="row" style="margin:8px 0 0"><button class="btn s" style="padding:6px 12px" onclick="rp('${m.id}')">↩ رد</button><button class="btn r" style="padding:6px 12px" onclick="dl('${m.id}')">🗑 مسح</button></div></div>`).join('')||'<span class="lbl">مفيش رسائل</span>'}catch(e){}}
const rp=id=>{$('#rp').value=id;$('.nv[data-t=send]').click();toast('اتحط ID الرد')};
const dl=async id=>{if(await act('delete',{channel:$('#tc').value,id},'اتمسحت'))msgs()};
$('#mb').onclick=()=>{const a=$('#ma').value;if(['ban','kick'].includes(a)&&!confirm('متأكد؟'))return;act('mod',{guild:$('#gs').value,user:$('#mu').value.trim(),action:a,minutes:+$('#mm').value||10},'اتنفذ ✓')};
const cv=$('#bg'),cx=cv.getContext('2d');let W,H,P=[];function rs(){W=cv.width=innerWidth;H=cv.height=innerHeight}rs();onresize=rs;
for(let i=0;i<70;i++)P.push({x:Math.random()*W,y:Math.random()*H,vx:(Math.random()-.5)*.5,vy:(Math.random()-.5)*.5});
(function d(){cx.clearRect(0,0,W,H);P.forEach((a,i)=>{a.x=(a.x+a.vx+W)%W;a.y=(a.y+a.vy+H)%H;cx.fillStyle='#b9a0ff99';cx.beginPath();cx.arc(a.x,a.y,1.6,0,7);cx.fill();for(let j=i+1;j<P.length;j++){const b=P[j],l=Math.hypot(a.x-b.x,a.y-b.y);if(l<120){cx.strokeStyle=`rgba(155,89,255,${.25*(1-l/120)})`;cx.beginPath();cx.moveTo(a.x,a.y);cx.lineTo(b.x,b.y);cx.stroke()}}});requestAnimationFrame(d)})();
if(TK)enter();
</script>
</body></html>'''
