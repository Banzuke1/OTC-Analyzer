"""
Lebegő jelzés-kártya más appok fölött (Draw over other apps).
FONTOS: a Java figyelők (listener) Python objektumait attribútumban
tartjuk meg, különben a Python szemétgyűjtő törli őket, és a Java egy
megszűnt objektumot hív -> natív összeomlás.
"""
try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android import mActivity
    from android.runnable import run_on_ui_thread
    ANDROID = True
except Exception:
    ANDROID = False
    def run_on_ui_thread(f):
        return f

try:
    import crash_logger
except Exception:
    crash_logger = None

def _safe_log(context):
    if crash_logger:
        crash_logger.log_exception(context)

BG_MAP = {"UP": 0xFF184D22, "DOWN": 0xFF4D1814, "WAIT": 0xFF2A2A30}
TEXT_MAP = {"UP": 0xFF3DDC5A, "DOWN": 0xFFFF5449, "WAIT": 0xFFBFBFC6}

def _s32(x):
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x

def _jstr(text):
    if not ANDROID:
        return text
    return autoclass('java.lang.String')(text)

def dp_to_px(dp_val):
    if not ANDROID:
        return dp_val
    Resources = autoclass('android.content.res.Resources')
    return int(dp_val * Resources.getSystem().getDisplayMetrics().density)


class FloatingSignal:
    def __init__(self, on_analyze=None):
        self.on_analyze = on_analyze
        self._card = None
        self._score_text = None
        self._detail_text = None
        self._params = None
        self._wm = None
        self._visible = False
        self._click_listener = None   # referencia megtartása
        self._touch_listener = None   # referencia megtartása

    def can_draw_overlays(self):
        if not ANDROID:
            return False
        return autoclass('android.provider.Settings').canDrawOverlays(mActivity)

    def request_permission(self):
        if not ANDROID:
            return
        Intent = autoclass('android.content.Intent')
        Settings = autoclass('android.provider.Settings')
        Uri = autoclass('android.net.Uri')
        intent = Intent(Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
                        Uri.parse("package:" + mActivity.getPackageName()))
        mActivity.startActivity(intent)

    @run_on_ui_thread
    def show(self):
        try:
            if not ANDROID or self._visible:
                return
            if not self.can_draw_overlays():
                self.request_permission()
                return

            LayoutParams = autoclass('android.view.WindowManager$LayoutParams')
            PixelFormat = autoclass('android.graphics.PixelFormat')
            Gravity = autoclass('android.view.Gravity')
            LinearLayout = autoclass('android.widget.LinearLayout')
            TextView = autoclass('android.widget.TextView')
            Button = autoclass('android.widget.Button')
            Context = autoclass('android.content.Context')
            Build = autoclass('android.os.Build$VERSION')
            GradientDrawable = autoclass('android.graphics.drawable.GradientDrawable')

            overlay_type = LayoutParams.TYPE_APPLICATION_OVERLAY if Build.SDK_INT >= 26 else LayoutParams.TYPE_PHONE
            self._params = LayoutParams(
                dp_to_px(210), -2, overlay_type,
                LayoutParams.FLAG_NOT_FOCUSABLE | LayoutParams.FLAG_LAYOUT_NO_LIMITS,
                PixelFormat.TRANSLUCENT)
            self._params.gravity = Gravity.TOP | Gravity.START
            self._params.x = dp_to_px(16)
            self._params.y = dp_to_px(120)

            ctx = mActivity.getApplicationContext()

            self._card = LinearLayout(ctx)
            self._card.setOrientation(LinearLayout.VERTICAL)
            pad = dp_to_px(10)
            self._card.setPadding(pad, pad, pad, pad)

            self._score_text = TextView(ctx)
            self._score_text.setText(_jstr("⚪ VÁRAKOZÁS  50/100"))
            self._score_text.setTextColor(_s32(TEXT_MAP["WAIT"]))
            self._score_text.setTextSize(16)
            self._card.addView(self._score_text)

            self._detail_text = TextView(ctx)
            self._detail_text.setText(_jstr("nincs adat még"))
            self._detail_text.setTextColor(_s32(0xFFAAAAB0))
            self._detail_text.setTextSize(11)
            self._detail_text.setPadding(0, dp_to_px(4), 0, dp_to_px(8))
            self._card.addView(self._detail_text)

            btn = Button(ctx)
            btn.setText(_jstr("Elemzés"))
            btn.setTextSize(13)
            btn.setAllCaps(False)
            self._click_listener = _ClickListener(self._on_click)
            btn.setOnClickListener(self._click_listener)
            self._card.addView(btn)

            self._touch_listener = _DragTouchListener(self._card, self._params, self)
            self._card.setOnTouchListener(self._touch_listener)

            self._set_card_bg("WAIT")
            self._wm = ctx.getSystemService(Context.WINDOW_SERVICE)
            self._wm.addView(self._card, self._params)
            self._visible = True
        except Exception:
            _safe_log("overlay show")

    def _on_click(self):
        if self.on_analyze:
            self.on_analyze()

    def _set_card_bg(self, direction):
        GradientDrawable = autoclass('android.graphics.drawable.GradientDrawable')
        d = GradientDrawable()
        d.setColor(_s32(BG_MAP.get(direction, BG_MAP["WAIT"])))
        d.setCornerRadius(dp_to_px(14))
        self._card.setBackground(d)

    @run_on_ui_thread
    def update(self, direction, score=0, quality="-", pattern="-", source=""):
        try:
            if not ANDROID or self._score_text is None:
                return
            label = {"UP": "🟢 BUY / UP", "DOWN": "🔴 SELL / DOWN", "WAIT": "⚪ VÁRAKOZÁS"}.get(direction, direction)
            self._score_text.setText(_jstr(f"{label}  {score}/100"))
            self._score_text.setTextColor(_s32(TEXT_MAP.get(direction, TEXT_MAP["WAIT"])))
            self._detail_text.setText(_jstr(f"{source} • {quality} • {pattern}"))
            self._set_card_bg(direction)
        except Exception:
            _safe_log("overlay update")

    @run_on_ui_thread
    def set_info(self, text):
        try:
            if ANDROID and self._detail_text is not None:
                self._detail_text.setText(_jstr(str(text)[:60]))
        except Exception:
            _safe_log("overlay set_info")

    @run_on_ui_thread
    def hide(self):
        try:
            if ANDROID and self._wm and self._visible:
                self._wm.removeView(self._card)
                self._visible = False
        except Exception:
            _safe_log("overlay hide")


if ANDROID:
    class _ClickListener(PythonJavaClass):
        __javainterfaces__ = ['android/view/View$OnClickListener']
        __javacontext__ = 'app'

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method('(Landroid/view/View;)V')
        def onClick(self, v):
            import threading
            def _run():
                try:
                    self.callback()
                except Exception:
                    _safe_log("overlay onClick")
            threading.Thread(target=_run, daemon=True).start()

    class _DragTouchListener(PythonJavaClass):
        __javainterfaces__ = ['android/view/View$OnTouchListener']
        __javacontext__ = 'app'

        def __init__(self, view, params, owner):
            super().__init__()
            self.view = view
            self.params = params
            self.owner = owner
            self.start_x = 0; self.start_y = 0
            self.touch_x = 0.0; self.touch_y = 0.0

        @java_method('(Landroid/view/View;Landroid/view/MotionEvent;)Z')
        def onTouch(self, v, event):
            try:
                action = event.getActionMasked()
                if action == 0:      # ACTION_DOWN
                    self.start_x = self.params.x
                    self.start_y = self.params.y
                    self.touch_x = event.getRawX()
                    self.touch_y = event.getRawY()
                    return True
                if action == 2:      # ACTION_MOVE
                    self.params.x = int(self.start_x + (event.getRawX() - self.touch_x))
                    self.params.y = int(self.start_y + (event.getRawY() - self.touch_y))
                    self.owner._wm.updateViewLayout(self.view, self.params)
                    return True
                return False
            except Exception:
                _safe_log("overlay onTouch")
                return False
