"""
Chart adapter: reconstructs approximate OHLC candles from a screenshot/frame
of a Pocket-Option-style candlestick chart, using color-based pixel analysis.

This does NOT read numeric prices off the screen (no OCR) - it reconstructs
a *relative* price scale from pixel Y positions. That's enough to feed the
existing technical indicators (EMA/RSI/ATR/support/resistance/patterns) in
main.py, since they only need consistent relative movement, not real
currency units.

Calibration:
- GREEN_RGB / RED_RGB: the bullish/bearish candle colors on your chart theme.
- roi: (left, top, right, bottom) as FRACTIONS of the full screenshot (0..1),
  so it doesn't depend on any one device's resolution.
"""
from PIL import Image

GREEN_RGB = (70, 183, 52)
RED_RGB = (255, 62, 31)
COLOR_TOLERANCE = 40

def _matches(px, target):
    r,g,b = px
    tr,tg,tb = target
    return abs(r-tr)<=COLOR_TOLERANCE and abs(g-tg)<=COLOR_TOLERANCE and abs(b-tb)<=COLOR_TOLERANCE

def _classify(px):
    if _matches(px, GREEN_RGB): return "G"
    if _matches(px, RED_RGB): return "R"
    return None

def extract_candles(frame, roi=(0.0, 0.20, 1.0, 0.58)):
    """
    frame: PIL.Image (RGB) - a full screenshot/captured frame.
    roi: fractional (left, top, right, bottom) crop of the chart area.
    Returns: list of (open, high, low, close) tuples, oldest first, in
    arbitrary pixel-derived units (NOT real prices).
    """
    W, H = frame.size
    left, top, right, bottom = roi
    x0, y0, x1, y1 = int(left*W), int(top*H), int(right*W), int(bottom*H)
    crop = frame.crop((x0, y0, x1, y1)).convert("RGB")
    cw, ch = crop.size
    px = crop.load()

    # classify every column: color + top/bottom extent of that color
    col_color = [None]*cw
    col_top = [None]*cw
    col_bot = [None]*cw
    for x in range(cw):
        top_y = None; bot_y = None
        counts = {"G":0, "R":0}
        for y in range(ch):
            c = _classify(px[x,y])
            if c:
                counts[c]+=1
                if top_y is None: top_y = y
                bot_y = y
        if top_y is not None:
            col_top[x]=top_y; col_bot[x]=bot_y
            col_color[x] = "G" if counts["G"]>=counts["R"] else "R"

    # cluster consecutive non-empty columns into candles, tolerating small
    # 1-2px gaps caused by JPEG/anti-aliasing so one candle isn't split in two
    GAP_TOLERANCE = 2
    candles_px = []
    x = 0
    while x < cw:
        if col_color[x] is None:
            x += 1; continue
        xs = x
        gap = 0
        while x < cw:
            if col_color[x] is not None:
                gap = 0
                x += 1
            elif gap < GAP_TOLERANCE:
                gap += 1
                x += 1
            else:
                x -= gap  # rewind the trailing gap, it belongs to next candle
                break
        xe = x  # [xs, xe)
        candles_px.append((xs, xe))

    candles = []
    for xs, xe in candles_px:
        width = xe - xs
        if width < 1:
            continue
        colors_here = [col_color[i] for i in range(xs, xe)]
        color = "G" if colors_here.count("G") >= colors_here.count("R") else "R"
        # high/low = extreme extent across ALL columns in this candle (wick included)
        tops = [col_top[i] for i in range(xs, xe) if col_top[i] is not None]
        bots = [col_bot[i] for i in range(xs, xe) if col_bot[i] is not None]
        if not tops:
            continue
        high_y = min(tops)   # smallest y = highest price
        low_y = max(bots)    # largest y = lowest price
        # body = extent typical of the EDGE columns (wick is centered & thinner)
        edge_n = max(1, width//4)
        edge_idx = list(range(xs, xs+edge_n)) + list(range(xe-edge_n, xe))
        edge_tops = [col_top[i] for i in edge_idx if col_top[i] is not None]
        edge_bots = [col_bot[i] for i in edge_idx if col_bot[i] is not None]
        body_top_y = min(edge_tops) if edge_tops else high_y
        body_bot_y = max(edge_bots) if edge_bots else low_y

        # convert pixel Y (down=low price) to price units (up=higher value)
        def price(y): return float(ch - y)

        if color == "G":
            close_p, open_p = price(body_top_y), price(body_bot_y)
        else:
            open_p, close_p = price(body_top_y), price(body_bot_y)
        high_p, low_p = price(high_y), price(low_y)
        candles.append((open_p, high_p, low_p, close_p))

    return candles


def rightmost_price_y(frame, roi=(0.0, 0.20, 1.0, 0.58), strip_frac=0.08):
    """A chart jobb szélén (a legfrissebb gyertya/ár-jelző helyén) lévő
    színes pixelek súlyközéppontjának Y pozícióját adja vissza, 0..1
    tartományban (0=felül, 1=alul) a ROI-n belül, vagy None-t, ha nincs
    ott színes pixel. Gyors, ismételt hívásra tervezve - a pillanatnyi
    ármozgás irányának/sebességének méréséhez, OCR nélkül."""
    W, H = frame.size
    left, top, right, bottom = roi
    x0, y0, x1, y1 = int(left*W), int(top*H), int(right*W), int(bottom*H)
    crop = frame.crop((x0, y0, x1, y1)).convert("RGB")
    cw, ch = crop.size
    strip_w = max(3, int(cw*strip_frac))
    px = crop.load()
    ys = []
    for x in range(max(0, cw-strip_w), cw):
        for y in range(ch):
            if _classify(px[x, y]):
                ys.append(y)
    if not ys:
        return None
    return (sum(ys)/len(ys)) / ch


def compute_velocity(y_positions):
    """y_positions: időrendi lista a jobb szél súlypont-pozícióiból (0..1).
    Visszaadja: (irány "UP"/"DOWN"/"WAIT", nagyság 0..1 relatív egységben).
    Mivel a képernyőn az Y lefelé nő, csökkenő Y = emelkedő ár."""
    ys = [y for y in y_positions if y is not None]
    if len(ys) < 3:
        return "WAIT", 0.0
    diffs = [ys[i+1]-ys[i] for i in range(len(ys)-1)]
    avg = sum(diffs)/len(diffs)
    mag = abs(avg)
    if avg < -0.004:
        return "UP", mag
    if avg > 0.004:
        return "DOWN", mag
    return "WAIT", mag


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else "6551.jpg"
    im = Image.open(path).convert("RGB")
    result = extract_candles(im)
    print(f"Detected {len(result)} candles")
    for c in result[-10:]:
        o,h,l,cl = c
        direction = "UP" if cl>o else "DOWN"
        print(f"  O={o:.1f} H={h:.1f} L={l:.1f} C={cl:.1f}  {direction}")
