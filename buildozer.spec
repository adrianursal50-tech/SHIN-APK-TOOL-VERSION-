[app]

title = SHIN
package.name = shindrakvex
package.domain = com.shin

source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,txt
source.include_patterns = main.py,DRAKVEX_ML.py,V2.py,skin_db.json

version = 1.0.0

requirements = python3,kivy==2.3.0,pycryptodome,zstandard,requests,urllib3,colorama,android

orientation = portrait
fullscreen = 0

android.permissions = INTERNET,ACCESS_NETWORK_STATE
android.api = 33
android.minapi = 24
android.ndk = 25b
android.archs = arm64-v8a, armeabi-v7a
android.accept_sdk_license = True
android.allow_backup = True

android.presplash_color = #0a0a0a
android.presplash_image = presplash.png
icon.filename = %(source.dir)s/icon.png

p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 0
