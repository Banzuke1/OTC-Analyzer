"""
Élő képernyőrögzítés Androidon (MediaProjection + pyjnius).
Android 14+ követelmények: előtér-szolgáltatás (mediaProjection típus),
és a MediaProjection.Callback regisztrálása a virtuális kijelző előtt.
Minden lépés státuszüzenetet ír (messages), hogy látható legyen, hol akad el.
"""
import io, threading, time, traceback
from collections import deque

try:
    from jnius import autoclass
    from android import activity, mActivity
    ANDROID = True
except Exception:
    ANDROID = False

try:
    import crash_logger
except Exception:
    crash_logger = None


def _to_bytes(arr):
    if isinstance(arr, (bytes, bytearray)):
        return bytes(arr)
    return bytes(bytearray([(b & 0xFF) for b in arr]))


class ScreenCapture:
    REQUEST_CODE = 4242

    def __init__(self, on_frame, interval=5.0):
        self.on_frame = on_frame
        self.interval = interval
        self.messages = deque(maxlen=60)
        self.running = False
        self._generation = 0
        self._projection = None
        self._virtual_display = None
        self._image_reader = None
        self._callback = None   # referenciák megtartása (GC ellen)
        self._handler = None
        self._wake = threading.Event()
        self._frames = 0
        if ANDROID:
            activity.bind(on_activity_result=self._on_activity_result)

    # ---------- segédek ----------
    def _status(self, msg):
        print("CAPTURE:", msg)
        self.messages.append(msg)

    def _log(self, ctx):
        self._status(f"HIBA ({ctx}): {traceback.format_exc().strip().splitlines()[-1][:160]}")
        if crash_logger:
            crash_logger.log_exception("capture " + ctx)

    def request_frame(self):
        self._wake.set()

    # ---------- indítás ----------
    def start(self):
        if not ANDROID:
            raise RuntimeError("Csak a telepített Android appban működik.")
        self.stop()
        Context = autoclass('android.content.Context')
        mgr = mActivity.getSystemService(Context.MEDIA_PROJECTION_SERVICE)
        intent = mgr.createScreenCaptureIntent()
        self._status("Engedély kérése (rögzítés)…")
        mActivity.startActivityForResult(intent, self.REQUEST_CODE)

    def _on_activity_result(self, requestCode, resultCode, data):
        if requestCode != self.REQUEST_CODE:
            return
        Activity = autoclass('android.app.Activity')
        if resultCode != Activity.RESULT_OK:
            self._status("Az engedély meg lett tagadva.")
            return
        self._status("Engedély megvan, beállítás…")
        self._generation += 1
        gen = self._generation
        threading.Thread(target=self._setup, args=(resultCode, data, gen), daemon=True).start()

    def _start_service(self):
        try:
            pkg = mActivity.getPackageName()
            Service = autoclass(pkg + '.ServiceCapture')
            Service.start(mActivity, '')
            self._status("Előtér-szolgáltatás elindítva.")
        except Exception:
            self._log("service start")

    def _setup(self, resultCode, data, gen):
        try:
            self._start_service()
            Context = autoclass('android.content.Context')
            mgr = mActivity.getSystemService(Context.MEDIA_PROJECTION_SERVICE)

            proj = None
            for attempt in range(12):
                time.sleep(0.8)
                try:
                    proj = mgr.getMediaProjection(resultCode, data)
                    if proj is not None:
                        break
                except Exception as e:
                    self._status(f"Projection {attempt+1}. próba: {type(e).__name__}: {str(e)[:90]}")
            if proj is None:
                self._status("HIBA: nem sikerült MediaProjection-t kapni.")
                return
            self._projection = proj
            self._status("MediaProjection kész.")

            # Android 14+: callback regisztrálása kötelező
            try:
                Handler = autoclass('android.os.Handler')
                Looper = autoclass('android.os.Looper')
                self._handler = Handler(Looper.getMainLooper())
                Cb = autoclass('org.otcanalyzer.Cb')
                self._callback = Cb()
                proj.registerCallback(self._callback, self._handler)
                self._status("Callback regisztrálva.")
            except Exception:
                self._log("registerCallback")

            DisplayMetrics = autoclass('android.util.DisplayMetrics')
            ImageReader = autoclass('android.media.ImageReader')
            PixelFormat = autoclass('android.graphics.PixelFormat')
            DisplayManager = autoclass('android.hardware.display.DisplayManager')
            metrics = DisplayMetrics()
            mActivity.getWindowManager().getDefaultDisplay().getRealMetrics(metrics)
            w, h, dpi = metrics.widthPixels, metrics.heightPixels, metrics.densityDpi

            self._image_reader = ImageReader.newInstance(w, h, PixelFormat.RGBA_8888, 2)
            self._virtual_display = proj.createVirtualDisplay(
                "otc_capture", w, h, dpi,
                DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
                self._image_reader.getSurface(), None, None)
            self._status(f"Virtuális kijelző kész ({w}x{h}).")
            self.running = True
            threading.Thread(target=self._loop, args=(w, h, gen), daemon=True).start()
        except Exception:
            self._log("setup")

    # ---------- képkocka ----------
    def _grab(self, w, h):
        from PIL import Image
        img = self._image_reader.acquireLatestImage()
        if img is None:
            return None
        try:
            plane = img.getPlanes()[0]
            buf = plane.getBuffer()
            pixel_stride = plane.getPixelStride()
            row_stride = plane.getRowStride()
            bw = row_stride // pixel_stride
            Bitmap = autoclass('android.graphics.Bitmap')
            Config = autoclass('android.graphics.Bitmap$Config')
            Fmt = autoclass('android.graphics.Bitmap$CompressFormat')
            BAOS = autoclass('java.io.ByteArrayOutputStream')
            bmp = Bitmap.createBitmap(bw, h, Config.ARGB_8888)
            bmp.copyPixelsFromBuffer(buf)
            if bw != w:
                cropped = Bitmap.createBitmap(bmp, 0, 0, w, h)
                bmp.recycle()
                bmp = cropped
            baos = BAOS()
            bmp.compress(Fmt.PNG, 100, baos)
            data = _to_bytes(baos.toByteArray())
            bmp.recycle()
            return Image.open(io.BytesIO(data)).convert("RGB")
        finally:
            img.close()

    def _loop(self, w, h, gen):
        time.sleep(1.0)
        while self.running and gen == self._generation:
            try:
                im = self._grab(w, h)
                if im is None:
                    self._status("Nincs új képkocka.")
                else:
                    self._frames += 1
                    if self.on_frame:
                        self.on_frame(im)
            except Exception:
                self._log("frame")
            self._wake.wait(self.interval)
            self._wake.clear()

    # ---------- leállítás ----------
    def stop(self):
        self.running = False
        self._generation += 1
        self._wake.set()
        for obj, meth in ((self._virtual_display, "release"),
                          (self._image_reader, "close"),
                          (self._projection, "stop")):
            try:
                if obj is not None:
                    getattr(obj, meth)()
            except Exception:
                pass
        self._virtual_display = self._image_reader = self._projection = None
        if ANDROID:
            try:
                Service = autoclass(mActivity.getPackageName() + '.ServiceCapture')
                Service.stop(mActivity)
            except Exception:
                pass
