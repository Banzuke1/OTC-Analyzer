# MediaProjection adapter

Android képernyő-hozzáféréshez natív MediaProjection komponens kell.
A Buildozer/Python UI önmagában nem tudja megbízhatóan kezelni minden
Android 13–16 eszköz gyártói korlátozását.

A projekt ezért külön adapterként kezeli:
1. MediaProjection permission
2. aktuális frame
3. chart ROI
4. gyertya pixel-felismerés
5. OHLC átadás az analyzer.py motorjának.

Ez szándékos: nem kerül bele olyan kód, amely valós OTC adatnak
hazudott véletlen/szintetikus adatot használna.
