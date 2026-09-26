"""
Live screen capture on Android via MediaProjection + pyjnius.
Only works in the built APK on a real device (not on desktop/Codespace).
"""
import threading
import time

try:
    from jnius import autoclass, PythonJavaClass, java_method
    from android import activity, mActivity
    ANDROID = True
except Exception:
    ANDROID = False


class ScreenCapture:
    def __init__(self, on_frame, interval=5.0):
        self.on_frame = on_frame
        self.interval = interval
        self._running = False
        self._projection = None
        self._virtual_display = None
        self._image_reader = None
        self._request_code = 4242
        if ANDROID:
            activity.bind(on_activity_result=self._on_activity_result)

    def request_permission(self):
        if not ANDROID:
            raise RuntimeError("Screen capture only works in the built Android app.")
        Context = autoclass('android.content.Context')
        MediaProjectionManager = autoclass('android.media.projection.MediaProjectionManager')
        mgr = mActivity.getSystemService(Context.MEDIA_PROJECTION_SERVICE)
        intent = mgr.createScreenCaptureIntent()
        mActivity.startActivityForResult(intent, self._request_code)

    def _on_activity_result(self, requestCode, resultCode, data):
        if requestCode != self._request_code:
            return
        Activity = autoclass('android.app.Activity')
        if resultCode != Activity.RESULT_OK:
            return
        Context = autoclass('android.content.Context')
        mgr = mActivity.getSystemService(Context.MEDIA_PROJECTION_SERVICE)
        self._projection = mgr.getMediaProjection(resultCode, data)
        self._start_virtual_display()

    def _start_virtual_display(self):
        DisplayMetrics = autoclass('android.util.DisplayMetrics')
        ImageReader = autoclass('android.media.ImageReader')
        PixelFormat = autoclass('android.graphics.PixelFormat')
        DisplayManager = autoclass('android.hardware.display.DisplayManager')

        metrics = DisplayMetrics()
        mActivity.getWindowManager().getDefaultDisplay().getRealMetrics(metrics)
        width, height, density = metrics.widthPixels, metrics.heightPixels, metrics.densityDpi

        self._image_reader = ImageReader.newInstance(width, height, PixelFormat.RGBA_8888, 2)
        self._virtual_display = self._projection.createVirtualDisplay(
            "otc_capture", width, height, density,
            DisplayManager.VIRTUAL_DISPLAY_FLAG_AUTO_MIRROR,
            self._image_reader.getSurface(), None, None
        )
        self._running = True
        threading.Thread(target=self._loop, args=(width, height), daemon=True).start()

    def _loop(self, width, height):
        from PIL import Image
        while self._running:
            try:
                img = self._image_reader.acquireLatestImage()
                if img is not None:
                    planes = img.getPlanes()
                    buf = planes[0].getBuffer()
                    pixel_stride = planes[0].getPixelStride()
                    row_stride = planes[0].getRowStride()
                    remaining = buf.remaining()
                    raw = bytes(bytearray(remaining))
                    buf.get(raw)
                    im = Image.frombuffer(
                        "RGBA", (row_stride // pixel_stride, height), raw, "raw", "RGBA", 0, 1
                    )
                    im = im.crop((0, 0, width, height)).convert("RGB")
                    img.close()
                    if self.on_frame:
                        self.on_frame(im)
            except Exception as e:
                print("ScreenCapture error:", e)
            time.sleep(self.interval)

    def stop(self):
        self._running = False
        if self._virtual_display:
            self._virtual_display.release()
        if self._projection:
            self._projection.stop()
