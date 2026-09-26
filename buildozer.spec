[app]
title = OTC Analyzer COMPLETE
package.name = otcanalyzer
package.domain = org.otcanalyzer
source.dir = .
source.include_exts = py,png,jpg,json,csv,kv
version = 1.0.0
requirements = python3,kivy
orientation = portrait
fullscreen = 0
android.api = 35
android.minapi = 24
android.archs = arm64-v8a
android.permissions = INTERNET,FOREGROUND_SERVICE,FOREGROUND_SERVICE_MEDIA_PROJECTION
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
