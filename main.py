import os, csv, time, random, threading
from collections import deque
from kivy.app import App
from kivy.clock import Clock
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.gridlayout import GridLayout
from kivy.uix.label import Label
from kivy.uix.button import Button
from kivy.graphics import Color, Rectangle

import crash_logger
crash_logger.install()

from chart_adapter import extract_candles, rightmost_price_y, compute_velocity
from roi_selector import ROISelector, load_roi, save_roi
try:
    from android_capture import ScreenCapture, ANDROID
except Exception:
    ScreenCapture, ANDROID = None, False
try:
    from overlay import FloatingSignal
except Exception:
    FloatingSignal = None

# Pillanatnyi sebesség mérése (Elemzés gombnál)
BURST_COUNT = 6          # ennyi képkockát próbál bekapni
BURST_INTERVAL = 0.25    # mp a kockák között
VELOCITY_MAX_AGE = 15.0  # mp - ennél régebbi sebesség-adatot nem használunk


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

def adx(c,n=14):
    if len(c)<n*2:return 0.0
    plus_dm=[];minus_dm=[];trs=[]
    for i in range(1,len(c)):
        o,h,l,cl=c[i];po,ph,pl,pc=c[i-1]
        up=h-ph;down=pl-l
        plus_dm.append(up if (up>down and up>0) else 0.0)
        minus_dm.append(down if (down>up and down>0) else 0.0)
        trs.append(max(h-l,abs(h-pc),abs(l-pc)))
    dx_values=[]
    for i in range(n,len(trs)+1):
        tr_n=sum(trs[i-n:i]) or 1e-9
        pdi=100*sum(plus_dm[i-n:i])/tr_n
        mdi=100*sum(minus_dm[i-n:i])/tr_n
        denom=pdi+mdi
        dx_values.append(100*abs(pdi-mdi)/denom if denom else 0.0)
    return sum(dx_values[-n:])/min(n,len(dx_values)) if dx_values else 0.0

def quality_label(v):
    if v>=27:return "MAGAS"
    if v>=20:return "KÖZEPES"
    return "ALACSONY"

def _ema_series(vals,n):
    if not vals:return []
    a=2/(n+1); out=[vals[0]]
    for v in vals[1:]:out.append(a*v+(1-a)*out[-1])
    return out

def macd(closes,fast=12,slow=26,signal=9):
    if len(closes)<slow+signal:return 0.0,0.0,0.0
    ef=_ema_series(closes,fast); es=_ema_series(closes,slow)
    macd_line=[f-s for f,s in zip(ef,es)]
    sig=_ema_series(macd_line,signal)
    return macd_line[-1], sig[-1], macd_line[-1]-sig[-1]

def stochastic(c,n=14,d=3):
    if len(c)<n+d:return 50.0,50.0
    closes=[x[3] for x in c]; highs=[x[1] for x in c]; lows=[x[2] for x in c]
    kv=[]
    for i in range(n,len(c)+1):
        hh=max(highs[i-n:i]); ll=min(lows[i-n:i])
        kv.append(100*(closes[i-1]-ll)/max(hh-ll,1e-9))
    return kv[-1], sum(kv[-d:])/min(d,len(kv))

def bollinger(closes,n=20,mult=2.0):
    if len(closes)<n:return 0.0,0.0,0.0
    window=closes[-n:]; mid=sum(window)/n
    var=sum((x-mid)**2 for x in window)/n
    sd=var**0.5
    return mid-mult*sd, mid, mid+mult*sd

def aggregate_candles(candles, group=3):
    """N gyertyát eggyé von össze -> szintetikus hosszabb idősík,
    a háttérben, a chart-váltás nélkül is elérhető többidősíkos
    megerősítéshez."""
    out=[]
    for i in range(0, len(candles)-group+1, group):
        chunk=candles[i:i+group]
        o=chunk[0][0]; cl=chunk[-1][3]
        h=max(x[1] for x in chunk); l=min(x[2] for x in chunk)
        out.append((o,h,l,cl))
    return out

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
    if len(c)<20:return {"direction":"WAIT","score":50,"confidence":50,"reason":"Kevés adat","adx":0,"quality":"ALACSONY","pattern":"n/a"}
    closes=[x[3] for x in c]
    e9,e21,e50=ema(closes,5),ema(closes,10),ema(closes,21)
    rr=rsi(closes,7); aa=atr(c); adxv=adx(c)
    macd_l,macd_s,macd_h=macd(closes,6,13,5)
    stoch_k,stoch_d=stochastic(c,14,3)
    bb_lo,bb_mid,bb_hi=bollinger(closes,20,2.0)
    mom=(closes[-1]-closes[-5])/max(abs(closes[-5]),1e-9)*100
    s=resistance(c); sup=support(c); last=closes[-1]
    score=50; reasons=[]; up_votes=0; down_votes=0

    if e9>e21:score+=12;reasons.append("EMA9>EMA21");up_votes+=1
    else:score-=12;reasons.append("EMA9<EMA21");down_votes+=1
    if e21>e50:score+=10;reasons.append("középtáv UP");up_votes+=1
    else:score-=10;reasons.append("középtáv DOWN");down_votes+=1
    if rr>60:score+=10;reasons.append("RSI bullish");up_votes+=1
    elif rr<40:score-=10;reasons.append("RSI bearish");down_votes+=1
    if macd_h>0:score+=8;reasons.append("MACD bullish");up_votes+=1
    elif macd_h<0:score-=8;reasons.append("MACD bearish");down_votes+=1
    if stoch_k>stoch_d and stoch_k<80:score+=6;reasons.append("Stoch bullish");up_votes+=1
    elif stoch_k<stoch_d and stoch_k>20:score-=6;reasons.append("Stoch bearish");down_votes+=1
    if last<=bb_lo:score+=6;reasons.append("ár az alsó Bollinger szalagnál (túladott)");up_votes+=1
    elif last>=bb_hi:score-=6;reasons.append("ár a felső Bollinger szalagnál (túlvett)");down_votes+=1
    score+=max(-10,min(10,mom*45))
    p=pattern(c)
    if "BULLISH" in p or p=="HAMMER":score+=7;up_votes+=1
    if "BEARISH" in p or p=="SHOOTING STAR":score-=7;down_votes+=1
    if last>sup and last<(sup+(s-sup)*.2):score+=3
    if last<s and last>(s-(s-sup)*.2):score-=3
    if adxv<18:
        score=50+(score-50)*0.3
        reasons.append("gyenge trend (ADX alacsony)")
    elif adxv>=25:
        reasons.append("erős trend (ADX magas)")
    score=max(0,min(100,round(score)))

    # Megegyezés-szavazás: a szükséges többség a piac állapotától függ -
    # erős trendnél elég 2 fő, bizonytalan (gyenge trendű) piacnál 4 fő
    # kell, hogy tényleg csak az egyértelmű esetekben adjon éles jelet.
    quality=quality_label(adxv)
    required_margin={"MAGAS":2,"KÖZEPES":3,"ALACSONY":4}[quality]
    if score>=60 and up_votes>=down_votes+required_margin:
        direction="UP"
    elif score<=40 and down_votes>=up_votes+required_margin:
        direction="DOWN"
    else:
        direction="WAIT"
        if score>=60 or score<=40:
            reasons.append(f"nincs elég megerősítés ({quality.lower()} piacnál {required_margin} kellene)")

    return {"direction":direction,"score":score,"confidence":abs(score-50)*2,
            "ema":(e9,e21,e50),"rsi":rr,"momentum":mom,"atr":aa,"adx":adxv,
            "macd":macd_h,"stoch_k":stoch_k,"stoch_d":stoch_d,
            "quality":quality,"votes":f"{up_votes}▲/{down_votes}▼",
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
        self.source="SZIM"
        self.app_active=True
        self._last_velocity=("WAIT",0.0)
        self._vel_ts=0.0
        self._awaiting_roi=False
        self._pending_roi_frame=None
        self.diag_lines=deque(maxlen=7)
        self.capture = ScreenCapture(on_frame=self._on_frame, interval=5.0) if (ANDROID and ScreenCapture) else None
        self.overlay = FloatingSignal(on_analyze=self.manual_refresh) if FloatingSignal else None
        self._data_dir = App.get_running_app().user_data_dir
        self.roi = load_roi(self._data_dir)
        self._last_crash = crash_logger.read_and_clear()
        self._build_main_ui()
        self.sim()
        Clock.schedule_interval(self._poll_capture, 0.7)

    # ---------- felület ----------
    def _build_main_ui(self):
        self.clear_widgets()
        self.add_widget(Label(text="OTC ANALYZER COMPLETE",font_size=sp(22),size_hint_y=None,height=dp(44)))
        if self._last_crash:
            cl = Label(text="ELŐZŐ ÖSSZEOMLÁS:\n"+self._last_crash[-1200:], font_size=sp(10),
                       halign="left", valign="top", size_hint_y=None, color=(1,0.5,0.5,1))
            cl.bind(width=lambda i,v: setattr(i,"text_size",(v,None)))
            cl.bind(texture_size=lambda i,v: setattr(i,"height",v[1]))
            self.add_widget(cl)
            d = Button(text="Hiba törlése",size_hint_y=None,height=dp(40))
            d.bind(on_release=lambda *_: self._dismiss_crash())
            self.add_widget(d)

        self.signal_bar = BoxLayout(size_hint_y=None, height=dp(70))
        with self.signal_bar.canvas.before:
            self._sig_color = Color(*SIGNAL_COLORS["WAIT"])
            self._sig_rect = Rectangle(pos=self.signal_bar.pos, size=self.signal_bar.size)
        self.signal_bar.bind(pos=self._sync_rect, size=self._sync_rect)
        self.signal_label = Label(text="VÁRAKOZÁS", font_size=sp(28), bold=True)
        self.signal_bar.add_widget(self.signal_label)
        self.add_widget(self.signal_bar)

        self.out=Label(text="",halign="left",valign="top",font_size=sp(15))
        self.out.bind(size=self._update_text_size)
        self.add_widget(self.out)

        self.diag=Label(text="\n".join(self.diag_lines),halign="left",valign="top",font_size=sp(10),
                        size_hint_y=None,height=dp(95),color=(0.6,0.9,1,1))
        self.diag.bind(size=self._update_text_size)
        self.add_widget(self.diag)

        row1=GridLayout(cols=3,size_hint_y=None,height=dp(50),spacing=dp(4))
        for t,f in [("SZIMULÁCIÓ",self.sim),("ÉLŐ MÓD",self.toggle_live),("OVERLAY",self.toggle_overlay)]:
            b=Button(text=t,font_size=sp(13));b.bind(on_release=f);row1.add_widget(b)
        self.add_widget(row1)

        row2=GridLayout(cols=4,size_hint_y=None,height=dp(50),spacing=dp(4))
        for t,f in [("TERÜLET",self.setup_roi),("WIN",lambda *_:self.mark("WIN")),
                    ("LOSS",lambda *_:self.mark("LOSS")),("NULL",lambda *_:self.mark("NULL"))]:
            b=Button(text=t,font_size=sp(12));b.bind(on_release=f);row2.add_widget(b)
        self.add_widget(row2)

        self.note=Label(text="DEMO/OKTATÁSI MÓD • nincs automatikus kötés",font_size=sp(11),
                        size_hint_y=None,height=dp(44))
        self.note.bind(size=self._update_text_size)
        self.add_widget(self.note)

    def _sync_rect(self, inst, val):
        self._sig_rect.pos = inst.pos
        self._sig_rect.size = inst.size

    def _update_text_size(self,inst,val):
        inst.text_size=(inst.width,None)

    def _dismiss_crash(self):
        self._last_crash=None
        self._build_main_ui()
        self._refresh_widgets()

    # ---------- diagnosztika ----------
    def _poll_capture(self, dt):
        if not self.capture: return
        new=[]
        while True:
            try: new.append(self.capture.messages.popleft())
            except IndexError: break
        if not new: return
        for m in new: self.diag_lines.append(m)
        if self.overlay and self.overlay._visible:
            self.overlay.set_info(new[-1])
        if self.app_active:
            self.diag.text="\n".join(self.diag_lines)

    def _msg(self, text):
        if self.capture: self.capture.messages.append(text)

    # ---------- adatforrás ----------
    def sim(self,*_):
        if self.live: self.toggle_live()
        self.source="SZIM"
        self.c.clear(); p=1.1700
        for _ in range(120):
            o=p; d=random.gauss(0,0.00022);cl=max(.0001,o+d)
            h=max(o,cl)+abs(random.gauss(0,.00007));l=min(o,cl)-abs(random.gauss(0,.00007))
            self.c.append((o,h,l,cl));p=cl
        self.run()

    def toggle_live(self,*_):
        if not self.capture:
            self.note.text="Élő mód csak a telepített Android appban működik."
            return
        if self.live:
            self.live=False
            self.capture.stop()
            self.source="SZIM"
            self.note.text="Élő mód leállítva."
            return
        self.c.clear(); self.source="ÉLŐ"; self.live=True
        try:
            self.capture.start()
            self.note.text="Élő mód: engedélyezd a képernyőmegosztást (teljes képernyő)."
        except Exception as e:
            self.live=False
            self.note.text=f"HIBA: {e}"

    def _on_frame(self, pil_image):
        """Rögzítő háttérszálról hívódik - csak GYŰJT, nem jelez.
        A tényleges jelzés csak az Elemzés gomb megnyomására történik."""
        if self._awaiting_roi:
            self._awaiting_roi=False
            self._pending_roi_frame=pil_image
            Clock.schedule_once(lambda dt: self._open_pending_roi())
            return
        candles = extract_candles(pil_image, roi=self.roi)
        if candles:
            self.c = deque(candles, maxlen=300)
        self._msg(f"Figyelés: {len(candles)} gyertya a képen (háttérben gyűjtve)")

    def manual_refresh(self):
        """Az Elemzés gomb hívja (bármelyikről). Élő módban gyors
        sorozatfelvételt indít (capture_burst): a legutolsó kockából friss
        gyertyákat olvas, a kockák sorozatából pedig a pillanatnyi
        ár-sebességet számolja, és csak utána elemez. Egyébként a már
        gyűjtött adatokból számol."""
        if self.live and self.capture and self.capture.running:
            self._msg("Elemzés: sorozatfelvétel indul…")
            self.capture.capture_burst(BURST_COUNT, BURST_INTERVAL, self._on_burst)
            return
        self._last_velocity=("WAIT",0.0)
        self.compute()
        Clock.schedule_once(lambda dt: self._refresh_widgets())

    def _on_burst(self, frames):
        """A sorozatfelvétel háttérszálából hívódik. A compute() DIREKT innen
        fut (nem Kivy Clock-on át), mert az app háttérben (Pocket Option
        előtérben) a Kivy ciklus szünetelhet, az overlay viszont így is
        frissül. Csak a Kivy widget-frissítés megy Clock-on át."""
        n=len(frames)
        try:
            if n:
                candles=extract_candles(frames[-1], roi=self.roi)
                if candles:
                    self.c=deque(candles, maxlen=300)
            ys=[rightmost_price_y(f, roi=self.roi) for f in frames]
            vdir,vmag=compute_velocity(ys)
            valid=len([y for y in ys if y is not None])
            self._last_velocity=(vdir,vmag)
            self._vel_ts=time.time()
            self._msg(f"Sebesség: {vdir} {vmag:.4f} ({n} új kocka, {valid} érvényes)")
        except Exception:
            crash_logger.log_exception("burst feldolgozás")
            self._last_velocity=("WAIT",0.0)
        try:
            self.compute()
        except Exception:
            crash_logger.log_exception("compute (burst után)")
        Clock.schedule_once(lambda dt: self._refresh_widgets())

    # ---------- terület kijelölés ----------
    def setup_roi(self,*_):
        if not (self.live and self.capture and self.capture.running):
            self.note.text="Előbb indítsd az ÉLŐ MÓD-ot és engedélyezd, majd nyomd meg újra."
            return
        self.note.text="Válts a Pocket Optionre! 7 mp múlva képet rögzítek, utána gyere vissza."
        threading.Timer(7.0, self._arm_roi).start()

    def _arm_roi(self):
        self._awaiting_roi=True
        if self.capture: self.capture.request_frame()

    def _open_pending_roi(self):
        if self._pending_roi_frame is None or not self.app_active:
            return
        frame=self._pending_roi_frame
        self._pending_roi_frame=None
        self.clear_widgets()
        self.add_widget(ROISelector(frame, on_save=self.on_roi_saved, on_cancel=self.close_roi_selector))

    def on_roi_saved(self, roi):
        self.roi=roi
        save_roi(self._data_dir, roi)
        self._build_main_ui(); self._refresh_widgets()
        self.note.text=f"Terület elmentve: {[round(v,2) for v in roi]}"

    def close_roi_selector(self):
        self._build_main_ui(); self._refresh_widgets()
        self.note.text="Terület beállítása megszakítva."

    # ---------- overlay ----------
    def toggle_overlay(self,*_):
        if not self.overlay:
            self.note.text="Overlay csak a telepített Android appban működik."
            return
        try:
            if self.overlay._visible:
                self.overlay.hide()
                self.note.text="Overlay elrejtve."
            else:
                self.overlay.show()
                self.note.text="Overlay parancs elküldve (ha engedély kell, engedélyezd, majd nyomd meg újra)."
        except Exception as e:
            self.note.text=f"OVERLAY HIBA: {type(e).__name__}: {str(e)[:150]}"

    # ---------- elemzés ----------
    def compute(self):
        """A trendet a LEZÁRT gyertyákból számoljuk (stabil). Három kemény
        kapu védi a jelet - bármelyik ellentmondása VÁRAKOZÁS-ra vált:
        1) hosszabb (szintetikus) idősík, 2) a most formálódó gyertya
        iránya, 3) a pillanatnyi ár-sebesség (csak élő módban, frissen
        mért sebességnél). Az, hogy melyik kapu blokkolt, a naplóba is
        bekerül."""
        candles=list(self.c)
        closed=candles; forming=None
        if self.source=="ÉLŐ" and len(candles)>21:
            closed=candles[:-1]
            forming=candles[-1]
        a=analyze(closed)
        a["pre_gate"]=a["direction"]
        a["blocked_by"]=""

        # 1) Többidősíkos kapu
        if a["direction"] in ("UP","DOWN"):
            higher=aggregate_candles(closed, group=3)
            a_higher=analyze(higher)
            a["higher_tf"]=a_higher["direction"]
            if a_higher["direction"]==a["direction"]:
                a["reason"]+=", hosszabb idősík is megerősíti"
            elif a_higher["direction"]!="WAIT":
                a["direction"]="WAIT"
                a["blocked_by"]="higher_tf"
                a["reason"]+=", de a hosszabb idősík ellentétes irányba mutat"

        # 2) Formálódó gyertya kapu
        if forming and a["direction"] in ("UP","DOWN"):
            fo,fh,fl,fc=forming
            forming_dir="UP" if fc>fo else "DOWN" if fc<fo else "WAIT"
            a["forming_bias"]=forming_dir
            if forming_dir==a["direction"]:
                a["reason"]+=", a jelenlegi gyertya is ebbe az irányba mozog"
            elif forming_dir!="WAIT":
                a["direction"]="WAIT"
                a["blocked_by"]="forming"
                a["reason"]+=", de a jelenlegi gyertya ellenkező irányba mozog"

        # 3) Pillanatnyi ár-sebesség kapu (csak friss mérésnél)
        vdir,vmag=self._last_velocity
        fresh=(time.time()-self._vel_ts)<VELOCITY_MAX_AGE
        a["velocity"]=(vdir,vmag) if (self.source=="ÉLŐ" and fresh) else ("WAIT",0.0)
        if self.source=="ÉLŐ" and fresh and a["direction"] in ("UP","DOWN"):
            if vdir==a["direction"]:
                a["reason"]+=", a pillanatnyi ármozgás is megerősíti"
            elif vdir!="WAIT":
                a["direction"]="WAIT"
                a["blocked_by"]="velocity"
                a["reason"]+=", de a pillanatnyi ármozgás ellentétes"

        self.last=a
        if self.overlay and self.overlay._visible:
            arrow={"UP":"↑","DOWN":"↓","WAIT":"–"}[a["velocity"][0]]
            self.overlay.update(a["direction"], a["score"], a.get("quality","-"),
                                a.get("pattern","-"), f"{self.source} {len(closed)}+1db v{arrow}")
        return a

    def run(self,*_):
        self.compute()
        self._refresh_widgets()

    def _refresh_widgets(self):
        """Csak a Kivy felületet frissíti, és csak ha az app előtérben van."""
        a=self.last
        if not self.app_active or not a:
            return
        self._sig_color.rgba=SIGNAL_COLORS.get(a["direction"], SIGNAL_COLORS["WAIT"])
        self.signal_label.text={"UP":"BUY / UP","DOWN":"SELL / DOWN","WAIT":"VÁRAKOZÁS"}[a["direction"]]
        vd,vm=a.get("velocity",("WAIT",0.0))
        self.out.text=(f"ADATFORRÁS: {self.source}  ({len(self.c)} gyertya)\n"
          f"SCORE: {a['score']}/100  |  CONFIDENCE: {a['confidence']}%  |  SZAVAZATOK: {a.get('votes','-')}\n"
          f"MINŐSÉG: {a.get('quality','-')}  |  ADX: {a.get('adx',0):.1f}\n"
          f"RSI(7): {a.get('rsi',50):.1f}  |  MACD hist: {a.get('macd',0):.5f}\n"
          f"Stoch K/D: {a.get('stoch_k',50):.1f}/{a.get('stoch_d',50):.1f}  |  Momentum: {a.get('momentum',0):.3f}%\n"
          f"Sebesség: {vd} ({vm:.4f})  |  Blokkolta: {a.get('blocked_by') or '-'}\n"
          f"Pattern: {a.get('pattern','-')}\n"
          f"Faktorok: {a.get('reason','-')}")

    def on_app_resume(self):
        self.app_active=True
        if self._pending_roi_frame is not None:
            self._open_pending_roi()
        else:
            self._refresh_widgets()

    def mark(self,result):
        if not self.last:return
        # új, bővebb napló (a régi signal_log.csv érintetlen marad)
        path=os.path.join(self._data_dir,"signal_log_v2.csv")
        exists=os.path.exists(path)
        a=self.last
        vd,vm=a.get("velocity",("WAIT",0.0))
        with open(path,"a",newline="",encoding="utf-8") as f:
            w=csv.writer(f)
            if not exists:
                w.writerow(["timestamp","source","direction","pre_gate","blocked_by","score","confidence",
                            "votes","rsi","adx","quality","pattern","macd","stoch_k","momentum",
                            "higher_tf","forming_bias","vel_dir","vel_mag","result"])
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"),self.source,a["direction"],
                        a.get("pre_gate",""),a.get("blocked_by",""),a["score"],a.get("confidence",""),
                        a.get("votes",""),round(a.get("rsi",50),2),round(a.get("adx",0),2),
                        a.get("quality",""),a.get("pattern",""),round(a.get("macd",0),6),
                        round(a.get("stoch_k",50),1),round(a.get("momentum",0),4),
                        a.get("higher_tf",""),a.get("forming_bias",""),vd,round(vm,5),result])
        self.note.text=f"Eredmény elmentve: {result}"


class OTCAnalyzerApp(App):
    def build(self): return AppUI()

    def on_pause(self):
        if self.root: self.root.app_active=False
        return True

    def on_resume(self):
        if self.root: self.root.on_app_resume()

if __name__=="__main__": OTCAnalyzerApp().run()
