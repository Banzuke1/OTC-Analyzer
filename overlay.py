"""
Compact floating badge with its own "Elemzés" (Analyze) button and a
colored signal readout, drawn over other apps (e.g. over Pocket Option)
using Android's "Draw over other apps" permission. Draggable to any
non-intrusive corner.
"""
try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android import mActivity
    ANDROID = True
except Exception:
    ANDROID = False

COLOR_MAP = {
    "UP":   0xFF22B233,
    "DOWN": 0xFFD92619,
    "WAIT": 0xFF59595E,
}

def _s32(x):
    """Konvertálja az ARGB hex értéket előjeles 32 bites Java int-té."""
    x &= 0xFFFFFFFF
    return x - 0x100000000 if x >= 0x80000000 else x

class FloatingSignal:
    def __init__(self, on_analyze=None):
        self.on_analyze = on_analyze
        self._container = None
        self._signal_text = None
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

        self._params = LayoutParams(
            dp_to_px(190), dp_to_px(52),
            overlay_type,
            LayoutParams.FLAG_NOT_FOCUSABLE | LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        )
        self._params.gravity = Gravity.TOP | Gravity.START
        self._params.x = dp_to_px(16)
        self._params.y = dp_to_px(120)

        self._container = LinearLayout(mActivity)
        self._container.setOrientation(LinearLayout.HORIZONTAL)
        bg = GradientDrawable(); bg.setColor(_s32(0xDD1A1A22)); bg.setCornerRadius(28)
        self._container.setBackground(bg)
        self._container.setPadding(dp_to_px(6), dp_to_px(4), dp_to_px(6), dp_to_px(4))

        analyze_btn = Button(mActivity)
        analyze_btn.setText("Elemzés")
        analyze_btn.setTextSize(12)
        analyze_btn.setAllCaps(False)
        analyze_btn.setOnClickListener(_ClickListener(self._on_click))
        self._container.addView(analyze_btn)

        self._signal_text = TextView(mActivity)
        self._signal_text.setText("⚪ WAIT")
        self._signal_text.setTextColor(Color.WHITE)
        self._signal_text.setTextSize(13)
        self._signal_text.setPadding(dp_to_px(10), 0, dp_to_px(4), 0)
        self._set_bg(self._signal_text, COLOR_MAP["WAIT"])
        self._container.addView(self._signal_text)

        self._container.setOnTouchListener(_DragTouchListener(self._container, self._params, self))

        self._wm = mActivity.getSystemService(Context.WINDOW_SERVICE)
        self._wm.addView(self._container, self._params)
        self._visible = True

    def _on_click(self):
        if self.on_analyze:
            self.on_analyze()

    def _set_bg(self, view, argb):
        GradientDrawable = autoclass('android.graphics.drawable.GradientDrawable')
        drawable = GradientDrawable()
        drawable.setColor(_s32(argb))
        drawable.setCornerRadius(20)
        view.setBackground(drawable)
        view.setPadding(dp_to_px(10), dp_to_px(6), dp_to_px(10), dp_to_px(6))

    def update(self, direction, extra=""):
        if not ANDROID or self._signal_text is None:
            return
        label = {"UP": "🟢 UP", "DOWN": "🔴 DOWN", "WAIT": "⚪ WAIT"}.get(direction, direction)
        self._set_bg(self._signal_text, COLOR_MAP.get(direction, COLOR_MAP["WAIT"]))
        self._signal_text.setText(f"{label} {extra}")

    def hide(self):
        if ANDROID and self._wm and self._visible:
            self._wm.removeView(self._container)
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
            self.moved = False

        @java_method('(Landroid/view/View;Landroid/view/MotionEvent;)Z')
        def onTouch(self, v, event):
            MotionEvent = autoclass('android.view.MotionEvent')
            action = event.getAction()
            if action == MotionEvent.ACTION_DOWN:
                self.start_x = self.params.x
                self.start_y = self.params.y
                self.touch_x = event.getRawX()
                self.touch_y = event.getRawY()
                self.moved = False
                return False
            elif action == MotionEvent.ACTION_MOVE:
                dx = event.getRawX() - self.touch_x
                dy = event.getRawY() - self.touch_y
                if abs(dx) > 8 or abs(dy) > 8:
                    self.moved = True
                    self.params.x = int(self.start_x + dx)
                    self.params.y = int(self.start_y + dy)
                    self.owner._wm.updateViewLayout(self.view, self.params)
                    return True
            return False
