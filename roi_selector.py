"""
Full-screen ROI (capture area) selector. Shows a frame captured from the
screen, and lets the user draw a rectangle over the actual candle chart
area with a simple drag. This makes the chart reading work with ANY
currency pair / chart layout, since the color-based detection itself
doesn't care which pair is shown - only where on screen the chart is.
"""
import os, json
from kivy.uix.floatlayout import FloatLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.image import Image
from kivy.graphics import Color, Line, Rectangle
from kivy.graphics.texture import Texture
from kivy.metrics import dp, sp

ROI_FILE = "roi_config.json"
DEFAULT_ROI = (0.0, 0.20, 1.0, 0.58)


def _roi_path(data_dir):
    return os.path.join(data_dir, ROI_FILE)


def load_roi(data_dir):
    try:
        with open(_roi_path(data_dir)) as f:
            roi = tuple(json.load(f)["roi"])
            if len(roi) == 4:
                return roi
    except Exception:
        pass
    return DEFAULT_ROI


def save_roi(data_dir, roi):
    try:
        with open(_roi_path(data_dir), "w") as f:
            json.dump({"roi": list(roi)}, f)
        return True
    except Exception:
        return False


def _pil_to_texture(pil_image):
    im = pil_image.convert("RGB")
    texture = Texture.create(size=im.size, colorfmt="rgb")
    texture.blit_buffer(im.tobytes(), colorfmt="rgb", bufferfmt="ubyte")
    texture.flip_vertical()
    return texture


class ROISelector(FloatLayout):
    """
    on_save(roi_tuple) - hívva, amikor a felhasználó elmenti a kijelölést
    on_cancel() - hívva, ha mégsem
    """
    def __init__(self, pil_image, on_save, on_cancel, **kw):
        super().__init__(**kw)
        self.on_save_cb = on_save
        self.on_cancel_cb = on_cancel
        self._p1 = None
        self._p2 = None

        self.bg_image = Image(texture=_pil_to_texture(pil_image),
                               allow_stretch=True, keep_ratio=False,
                               size_hint=(1, 1), pos_hint={"x": 0, "y": 0})
        self.add_widget(self.bg_image)

        self.hint = Label(
            text="Húzd egy téglalapba a chart (gyertyák) területét, majd Mentés",
            size_hint=(1, None), height=dp(60), pos_hint={"x": 0, "top": 1},
            font_size=sp(15), bold=True,
            color=(1, 1, 1, 1)
        )
        with self.hint.canvas.before:
            Color(0, 0, 0, 0.65)
            self._hint_bg = Rectangle(pos=self.hint.pos, size=self.hint.size)
        self.hint.bind(pos=self._sync_hint_bg, size=self._sync_hint_bg)
        self.add_widget(self.hint)

        btn_row = FloatLayout(size_hint=(1, None), height=dp(60), pos_hint={"x": 0, "y": 0})
        save_btn = Button(text="Mentés", size_hint=(0.5, 1), pos_hint={"x": 0, "y": 0})
        cancel_btn = Button(text="Mégse", size_hint=(0.5, 1), pos_hint={"x": 0.5, "y": 0})
        save_btn.bind(on_release=self._save)
        cancel_btn.bind(on_release=lambda *_: self.on_cancel_cb())
        btn_row.add_widget(save_btn)
        btn_row.add_widget(cancel_btn)
        self.add_widget(btn_row)

    def _sync_hint_bg(self, *_):
        self._hint_bg.pos = self.hint.pos
        self._hint_bg.size = self.hint.size

    def on_touch_down(self, touch):
        if touch.y > self.height - dp(60) or touch.y < dp(60):
            return super().on_touch_down(touch)
        self._p1 = touch.pos
        self._p2 = touch.pos
        self._redraw()
        return True

    def on_touch_move(self, touch):
        if self._p1 is not None:
            self._p2 = touch.pos
            self._redraw()
            return True
        return super().on_touch_move(touch)

    def on_touch_up(self, touch):
        if self._p1 is not None:
            self._p2 = touch.pos
            self._redraw()
        return super().on_touch_up(touch)

    def _redraw(self):
        self.canvas.after.clear()
        if not (self._p1 and self._p2):
            return
        x1, y1 = self._p1; x2, y2 = self._p2
        with self.canvas.after:
            Color(0.2, 0.8, 1.0, 1)
            Line(rectangle=(min(x1, x2), min(y1, y2), abs(x2 - x1), abs(y2 - y1)), width=dp(2))

    def _save(self, *_):
        if not (self._p1 and self._p2):
            self.on_cancel_cb()
            return
        x1, y1 = self._p1; x2, y2 = self._p2
        w, h = self.width, self.height
        left = min(x1, x2) / w
        right = max(x1, x2) / w
        top = 1 - (max(y1, y2) / h)
        bottom = 1 - (min(y1, y2) / h)
        roi = (max(0.0, left), max(0.0, top), min(1.0, right), min(1.0, bottom))
        self.on_save_cb(roi)
