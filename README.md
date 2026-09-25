# OTC Analyzer COMPLETE

Cél: Pocket Option OTC chart képernyőalapú, demo/oktatási elemzése.
Nincs automatikus kötés és nincs Pocket Option-bejelentkezés.

A projekt tartalmazza az Android UI-t, indikátormotort, naplózást,
szimulációt, CSV exportot és Android Studio nélküli GitHub Actions buildet.

Fontos: a tényleges Pocket Option képernyőképfeldolgozás Androidon
MediaProjection integrációt igényel; ebben a csomagban az elemzőmotor
és a teljes kezelőfelület kész, a chart-felismerés pedig külön adapterként
van kialakítva, hogy az eszközönkénti tesztelés során cserélhető legyen.

Build:
1. Töltsd fel GitHub repositoryba.
2. Actions -> Build APK -> Run workflow.
3. Artifact: OTC-Analyzer-APK.
