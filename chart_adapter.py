"""
Chart adapter interface.

Android MediaProjection frames should be passed to extract_candles(frame).
The function intentionally does not perform Pocket Option clicks or trades.
A production device-specific adapter can crop the selected chart ROI and
estimate candle OHLC from pixel geometry/colors.
"""
def extract_candles(frame, roi):
    # Returns [] until a calibrated chart ROI adapter is connected.
    # Keeping this explicit prevents fake market data from being presented
    # as real OTC data.
    return []
