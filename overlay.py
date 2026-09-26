"""
Small always-on-top floating signal badge, drawn over other apps
(e.g. over the Pocket Option app) using Android's "Draw over other apps"
permission. Shows a colored badge (UP/DOWN/WAIT) that can be dragged to
a non-intrusive corner.
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

class FloatingSignal:
    def __init__(self):
        self._view = None
        self._params = None
        self._wm = None
        self._text = None
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
        TextView = autoclass('android.widget.TextView')
        Context = autoclass('android.content.Context')
        Build = autoclass('android.os.Build$VERSION')
        Color = autoclass('android.graphics.Color')

        overlay_type = LayoutParams.TYPE_APPLICATION_OVERLAY if Build.SDK_INT >= 26 else LayoutParams.TYPE_PHONE

        self._params = LayoutParams(
            dp_to_px(120), dp_to_px(48),
            overlay_type,
            LayoutParams.FLAG_NOT_FOCUSABLE | LayoutParams.FLAG_LAYOUT_NO_LIMITS,
            PixelFormat.TRANSLUCENT
        )
        self._params.gravity = Gravity.TOP | Gravity.START
        self._params.x = dp_to_px(16)
        self._params.y = dp_to_px(120)

        self._text = TextView(mActivity)
        self._text.setText("⚪ WAIT")
        self._text.setTextColor(Color.WHITE)
        self._text.setTextSize(14)
        self._text.setGravity(Gravity.CENTER)
        self._set_bg(COLOR_MAP["WAIT"])
        self._text.setOnTouchListener(_DragTouchListener(self._text, self._params, self))

        self._wm = mActivity.getSystemService(Context.WINDOW_SERVICE)
        self._wm.addView(self._text, self._params)
        self._visible = True

    def _set_bg(self, argb):
        if not ANDROID or self._text is None:
            return
        GradientDrawable = autoclass('android.graphics.drawable.GradientDrawable')
        drawable = GradientDrawable()
        drawable.setColor(argb)
        drawable.setCornerRadius(24)
        self._text.setBackground(drawable)

    def update(self, direction, extra=""):
        if not ANDROID or self._text is None:
            return
        label = {"UP": "🟢 UP", "DOWN": "🔴 DOWN", "WAIT": "⚪ WAIT"}.get(direction, direction)
        self._set_bg(COLOR_MAP.get(direction, COLOR_MAP["WAIT"]))
        self._text.setText(f"{label} {extra}")

    def hide(self):
        if ANDROID and self._wm and self._visible:
            self._wm.removeView(self._text)
            self._visible = False


def dp_to_px(dp_val):
    if not ANDROID:
        return dp_val
    Resources = autoclass('android.content.res.Resources')
    density = Resources.getSystem().getDisplayMetrics().density
    return int(dp_val * density)


if ANDROID:
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
                return True
            elif action == MotionEvent.ACTION_MOVE:
                self.params.x = int(self.start_x + (event.getRawX() - self.touch_x))
                self.params.y = int(self.start_y + (event.getRawY() - self.touch_y))
                self.owner._wm.updateViewLayout(self.view, self.params)
                return True
            return False
