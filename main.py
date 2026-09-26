import os, csv, time, math, random
from collections import deque
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.uix.spinner import Spinner
from kivy.graphics import Color, Rectangle

from chart_adapter import extract_candles
try:
    from android_capture import ScreenCapture, ANDROID
except Exception:
    ScreenCapture, ANDROID = None, False
try:
    from overlay import FloatingSignal
except Exception:
    FloatingSignal = None

LOG=os.path.join(os.path.dirname(__file__),"signal_log.csv")

def ema(x,n):
    if not x:return 0.0
    a=2/(n+1); e=float(x[0])
    for v in x[1:]:e=a*float(v)+(1-a)*e
    return e

def rsi(x,n=14):
    if len(x)<n+1:return 50.0
    g=[];l=[]
    for a,b in zip(x[-n-1:-1],x[-n:]):
        d=b-a;g.append(max(d,0));l.append(max(-d,0))
    ag=sum(g)/n; al=sum(l)/n
    return 100.0 if al==0 else 100-100/(1+ag/al)

def atr(c,n=14):
    if len(c)<2:return 0
    t=[]
    for i in range(1,len(c)):
        o,h,l,cl=c[i];pc=c[i-1][3]
        t.append(max(h-l,abs(h-pc),abs(l-pc)))
    return sum(t[-n:])/min(n,len(t))

def support(c,n=30):
    return min(x[2] for x in c[-n:]) if c else 0

def resistance(c,n=30):
    return max(x[1] for x in c[-n:]) if c else 0

def pattern(c):
    if len(c)<3:return "n/a"
    o,h,l,cl=c[-1]; po,ph,pl,pc=c[-2]
    body=abs(cl-o); rng=max(h-l,1e-9)
    if body/rng<.12:return "DOJI"
    if cl>o and pc<po and cl>=po and o<=pc:return "BULLISH ENGULFING"
    if cl<o and pc>po and cl<=po and o>=pc:return "BEARISH ENGULFING"
    upper=h-max(o,cl); lower=min(o,cl)-l
    if lower>body*2 and upper<body:return "HAMMER"
    if upper>body*2 and lower<body:return "SHOOTING STAR"
    return "BULLISH" if cl>o else "BEARISH"

def analyze(c):
    if len(c)<20:return {"direction":"WAIT","score":50,"confidence":50,"reason":"Kevés adat"}
    closes=[x[3] for x in c]
    e9,e21,e50=ema(closes,9),ema(closes,21),ema(closes,50)
    rr=rsi(closes); aa=atr(c)
    mom=(closes[-1]-closes[-5])/max(abs(closes[-5]),1e-9)*100
    s=resistance(c); sup=support(c); last=closes[-1]
    score=50; reasons=[]
    if e9>e21:score+=12;reasons.append("EMA9>EMA21")
    else:score-=12;reasons.append("EMA9<EMA21")
    if e21>e50:score+=10;reasons.append("középtáv UP")
    else:score-=10;reasons.append("középtáv DOWN")
    if rr>55:score+=10;reasons.append("RSI bullish")
    elif rr<45:score-=10;reasons.append("RSI bearish")
    score+=max(-10,min(10,mom*45))
    p=pattern(c)
    if "BULLISH" in p or p=="HAMMER":score+=7
    if "BEARISH" in p or p=="SHOOTING STAR":score-=7
    if last>sup and last<(sup+(s-sup)*.2):score+=3
    if last<s and last>(s-(s-sup)*.2):score-=3
    score=max(0,min(100,round(score)))
    direction="UP" if score>=60 else "DOWN" if score<=40 else "WAIT"
    return {"direction":direction,"score":score,"confidence":abs(score-50)*2,
            "ema":(e9,e21,e50),"rsi":rr,"momentum":mom,"atr":aa,
            "support":sup,"resistance":s,"pattern":p,"reason":", ".join(reasons)}

SIGNAL_COLORS = {
    "UP":   (0.13, 0.70, 0.20, 1),
    "DOWN": (0.85, 0.15, 0.10, 1),
    "WAIT": (0.35, 0.35, 0.38, 1),
}

class AppUI(BoxLayout):
    def __init__(self,**kw):
        super().__init__(orientation="vertical",padding=dp(8),spacing=dp(6),**kw)
        self.c=deque(maxlen=300); self.last=None
        self.live=False
        self.capture=None
        self.overlay = FloatingSignal() if FloatingSignal else None

        self.add_widget(Label(text="OTC ANALYZER COMPLETE",font_size=sp(24),size_hint_y=None,height=dp(50)))

        top=GridLayout(cols=2,size_hint_y=None,height=dp(100))
        self.pair=Spinner(text="EUR/USD OTC",values=("EUR/USD OTC","GBP/USD OTC","USD/JPY OTC","AUD/USD OTC"))
        self.tf=Spinner(text="M5",values=("S3","S5","S15","M1","M5","M15","M30"))
        top.add_widget(Label(text="Pár"));top.add_widget(self.pair)
        top.add_widget(Label(text="Idősík"));top.add_widget(self.tf)
        self.add_widget(top)

        self.signal_bar = BoxLayout(size_hint_y=None, height=dp(70))
        with self.signal_bar.canvas.before:
            self._sig_color = Color(*SIGNAL_COLORS["WAIT"])
            self._sig_rect = Rectangle(pos=self.signal_bar.pos, size=self.signal_bar.size)
        self.signal_bar.bind(pos=self._sync_rect, size=self._sync_rect)
        self.signal_label = Label(text="VÁRAKOZÁS", font_size=sp(28), bold=True)
        self.signal_bar.add_widget(self.signal_label)
        self.add_widget(self.signal_bar)

        self.out=Label(text="",halign="left",valign="top",font_size=sp(16))
        self.out.bind(size=self._update_text_size)
        self.add_widget(self.out)

        row=GridLayout(cols=3,size_hint_y=None,height=dp(50),spacing=dp(4))
        for t,f in [("SZIMULÁCIÓ",self.sim),("ÉLŐ MÓD",self.toggle_live),("OVERLAY",self.toggle_overlay),
                    ("ELEMZÉS",self.run),("WIN",lambda *_:self.mark("WIN")),("LOSS",lambda *_:self.mark("LOSS")),("NULL",lambda *_:self.mark("NULL"))]:
            b=Button(text=t);b.bind(on_release=f);row.add_widget(b)
        self.add_widget(row)

        self.note=Label(text="DEMO/OKTATÁSI MÓD • nincs automatikus kötés",font_size=sp(12),size_hint_y=None,height=dp(30))
        self.add_widget(self.note)
        self.sim()

    def _sync_rect(self, inst, val):
        self._sig_rect.pos = inst.pos
        self._sig_rect.size = inst.size

    def _update_text_size(self,inst,val):
        inst.text_size=(inst.width,None)

    def sim(self,*_):
        if self.live: self.toggle_live()
        self.c.clear(); p=1.1700
        for _ in range(120):
            o=p; d=random.gauss(0,0.00022);cl=max(.0001,o+d)
            h=max(o,cl)+abs(random.gauss(0,.00007));l=min(o,cl)-abs(random.gauss(0,.00007))
            self.c.append((o,h,l,cl));p=cl
        self.run()

    def toggle_live(self,*_):
        if not ANDROID or ScreenCapture is None:
            self.note.text="Élő mód csak a telepített Android appban működik."
            return
        if self.live:
            self.live=False
            if self.capture: self.capture.stop()
            self.note.text="Élő mód leállítva."
            return
        self.c.clear()
        self.capture = ScreenCapture(on_frame=self._on_frame, interval=5.0)
        self.capture.request_permission()
        self.live=True
        self.note.text="Élő mód: engedélyt kérünk a képernyőrögzítéshez…"

    def _on_frame(self, pil_image):
        candles = extract_candles(pil_image)
        added = 0
        if candles:
            for cndl in candles[-5:]:
                if cndl not in self.c:
                    self.c.append(cndl); added += 1
        status = f"Élő mód aktív • {len(candles)} gyertya a képen • {len(self.c)} eltárolva"
        Clock.schedule_once(lambda dt: self._update_live_status(status))

    def _update_live_status(self, status):
        self.note.text = status
        self.run()

    def toggle_overlay(self,*_):
        if not self.overlay:
            self.note.text="Overlay csak a telepített Android appban működik."
            return
        if self.overlay._visible:
            self.overlay.hide()
            self.note.text="Overlay elrejtve."
        else:
            self.overlay.show()
            self.note.text="Overlay bekapcsolva (ha nem látszik, engedélyezd a 'Megjelenítés más appok felett' opciót, majd nyomd meg újra)."

    def run(self,*_):
        self.last=analyze(list(self.c));a=self.last
        col = SIGNAL_COLORS.get(a["direction"], SIGNAL_COLORS["WAIT"])
        self._sig_color.rgba = col
        self.signal_label.text = {"UP":"🟢 BUY / UP","DOWN":"🔴 SELL / DOWN","WAIT":"⚪ VÁRAKOZÁS"}[a["direction"]]
        if self.overlay and self.overlay._visible:
            self.overlay.update(a["direction"], extra=f"{a['score']}")
        self.out.text=(f"{self.pair.text}   |   {self.tf.text}\n\n"
          f"MODEL SCORE: {a['score']}/100   |   CONFIDENCE: {a['confidence']}%\n\n"
          f"EMA 9/21/50: {a.get('ema',('-','-','-'))}\n"
          f"RSI(14): {a.get('rsi',50):.1f}\n"
          f"Momentum: {a.get('momentum',0):.3f}%\n"
          f"ATR: {a.get('atr',0):.6f}\n"
          f"Support: {a.get('support',0):.5f}\n"
          f"Resistance: {a.get('resistance',0):.5f}\n"
          f"Pattern: {a.get('pattern','-')}\n\n"
          f"Faktorok: {a.get('reason','-')}")

    def mark(self,result):
        if not self.last:return
        exists=os.path.exists(LOG)
        with open(LOG,"a",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            if not exists:w.writerow(["timestamp","pair","tf","direction","score","confidence","rsi","momentum","atr","pattern","result"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"),self.pair.text,self.tf.text,
                        self.last["direction"],self.last["score"],self.last["confidence"],
                        round(self.last.get("rsi",50),2),round(self.last.get("momentum",0),5),
                        round(self.last.get("atr",0),8),self.last.get("pattern",""),result])
        self.note.text=f"Eredmény elmentve: {result}"

class OTCAnalyzerApp(App):
    def build(self): return AppUI()

if __name__=="__main__": OTCAnalyzerApp().run()
