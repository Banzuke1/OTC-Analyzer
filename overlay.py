"""
Compact floating signal card, drawn over other apps (e.g. Pocket Option)
using Android's "Draw over other apps" permission. Shows the current
score/direction, quality (ADX-based) and detected candle pattern, plus
its own "Elemzés" (Analyze) button. Draggable to any corner.
"""
try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android import mActivity
    ANDROID = True
except Exception:
    ANDROID = False

BG_MAP = {
    "UP":   0xFF184D22,
    "DOWN": 0xFF4D1814,
    "WAIT": 0xFF2A2A30,
}
TEXT_MAP = {
    "UP":   0xFF3DDC5A,
    "DOWN": 0xFFFF5449,
    "WAIT": 0xFFBFBFC6,
}

def _s32(x):
    """Konvertálja az ARGB hex értéket előjeles 32 bites Java int-té."""
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x

def _jstr(text):
    """Explicit Java String objektum, hogy a pyjnius biztosan a
    setText(CharSequence) túlterhelést válassza."""
    if not ANDROID:
        return text
    JString = autoclass('java.lang.String')
    return JString(text)


class FloatingSignal:
    def __init__(self, on_analyze=None):
        self.on_analyze = on_analyze
        self._card = None
        self._score_text = None
        self._detail_text = None
        self._params = None
        self._wm = None
        self._visible = False

    def can_draw_overlays(self):
        if not ANDROID:
            return False
        Settings = autoclass('android.provider.Settings')
        return Settings.canDrawOverlays(mActivity)

    def request_permission(self):
        if not ANDROID:
            return
        Intent = autoclass('android.content.Intent')
        Settings = autoclass('android.provider.Settings')
        Uri = autoclass('android.net.Uri')
        intent = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:" + mActivity.getPackageName())
        )
        mActivity.startActivity(intent)

    def show(self):
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
        Color = autoclass('android.graphics.Color')
        GradientDrawable = autoclass('android.graphics.drawable.GradientDrawable')

        overlay_type = LayoutParams.TYPE_APPLICATION_OVERLAY if Build.SDK_INT >= 26 else LayoutParams.TYPE_PHONE
        WRAP_CONTENT = -2

        self._params = LayoutParams(
            dp_to_px(210), WRAP_CONTENT,
            overlay_type,
            LayoutParams.FLAG_NOT_FOCUSABLE | LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        )
        self._params.gravity = Gravity.TOP | Gravity.START
        self._params.x = dp_to_px(16)
        self._params.y = dp_to_px(120)

        self._card = LinearLayout(mActivity)
        self._card.setOrientation(LinearLayout.VERTICAL)
        bg = GradientDrawable(); bg.setColor(_s32(0xF0141418)); bg.setCornerRadius(dp_to_px(14))
        self._card.setBackground(bg)
        pad = dp_to_px(10)
        self._card.setPadding(pad, pad, pad, pad)

        self._score_text = TextView(mActivity)
        self._score_text.setText(_jstr("⚪ VÁRAKOZÁS  50/100"))
        self._score_text.setTextColor(_s32(TEXT_MAP["WAIT"]))
        self._score_text.setTextSize(16)
        self._card.addView(self._score_text)

        self._detail_text = TextView(mActivity)
        self._detail_text.setText(_jstr("Minőség: -  •  Minta: -"))
        self._detail_text.setTextColor(_s32(0xFFAAAAB0))
        self._detail_text.setTextSize(11)
        self._detail_text.setPadding(0, dp_to_px(4), 0, dp_to_px(8))
        self._card.addView(self._detail_text)

        analyze_btn = Button(mActivity)
        analyze_btn.setText(_jstr("Elemzés"))
        analyze_btn.setTextSize(13)
        analyze_btn.setAllCaps(False)
        analyze_btn.setOnClickListener(_ClickListener(self._on_click))
        self._card.addView(analyze_btn)

        self._card.setOnTouchListener(_DragTouchListener(self._card, self._params, self))

        self._set_card_bg("WAIT")

        self._wm = mActivity.getSystemService(Context.WINDOW_SERVICE)
        self._wm.addView(self._card, self._params)
        self._visible = True

    def _on_click(self):
        if self.on_analyze:
            self.on_analyze()

    def _set_card_bg(self, direction):
        GradientDrawable = autoclass('android.graphics.drawable.GradientDrawable')
        drawable = GradientDrawable()
        drawable.setColor(_s32(BG_MAP.get(direction, BG_MAP["WAIT"])))
        drawable.setCornerRadius(dp_to_px(14))
        self._card.setBackground(drawable)

    def update(self, direction, score=0, quality="-", pattern="-"):
        if not ANDROID or self._score_text is None:
            return
        label = {"UP": "🟢 BUY / UP", "DOWN": "🔴 SELL / DOWN", "WAIT": "⚪ VÁRAKOZÁS"}.get(direction, direction)
        self._score_text.setText(_jstr(f"{label}  {score}/100"))
        self._score_text.setTextColor(_s32(TEXT_MAP.get(direction, TEXT_MAP["WAIT"])))
        self._detail_text.setText(_jstr(f"Minőség: {quality}  •  Minta: {pattern}"))
        self._set_card_bg(direction)

    def hide(self):
        if ANDROID and self._wm and self._visible:
            self._wm.removeView(self._card)
            self._visible = False


def dp_to_px(dp_val):
    if not ANDROID:
        return dp_val
    Resources = autoclass('android.content.res.Resources')
    density = Resources.getSystem().getDisplayMetrics().density
    return int(dp_val * density)


if ANDROID:
    class _ClickListener(PythonJavaClass):
        __javainterfaces__ = ['android/view/View$OnClickListener']
        __javacontext__ = 'app'

        def __init__(self, callback):
            super().__init__()
            self.callback = callback

        @java_method('(Landroid/view/View;)V')
        def onClick(self, v):
            self.callback()

    class _DragTouchListener(PythonJavaClass):
        __javainterfaces__ = ['android/view/View$OnTouchListener']
        __javacontext__ = 'app'

        def __init__(self, view, params, owner):
            super().__init__()
            self.view = view
            self.params = params
            self.owner = owner
            self.start_x = 0; self.start_y = 0
            self.touch_x = 0; self.touch_y = 0

        @java_method('(Landroid/view/View;Landroid/view/MotionEvent;)Z')
        def onTouch(self, v, event):
            MotionEvent = autoclass('android.view.MotionEvent')
            action = event.getAction()
            if action == MotionEvent.ACTION_DOWN:
                self.start_x = self.params.x
                self.start_y = self.params.y
                self.touch_x = event.getRawX()
                self.touch_y = event.getRawY()
                return False
            elif action == MotionEvent.ACTION_MOVE:
                dx = event.getRawX() - self.touch_x
                dy = event.getRawY() - self.touch_y
                if abs(dx) > 8 or abs(dy) > 8:
                    self.params.x = int(self.start_x + dx)
                    self.params.y = int(self.start_y + dy)
                    self.owner._wm.updateViewLayout(self.view, self.params)
                    return True
            return False
