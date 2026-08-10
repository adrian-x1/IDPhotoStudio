# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path
import re
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs


# Platform icons are optional: a missing file must not break the build, since
# `python -m PyInstaller build.spec` also runs on developer machines that have
# not generated them yet.
def _icon(name: str) -> str | None:
    path = Path("assets") / name
    return str(path) if path.is_file() else None


mac_icon = _icon("icon.icns")
windows_icon = _icon("icon.ico")

# Apple wants one to three dot-separated integers, so a branch name from a
# manual run has to fall back rather than be passed through.
app_version = os.environ.get("APP_VERSION", "").lstrip("v")
if not re.fullmatch(r"\d+(\.\d+){0,2}", app_version):
    app_version = "0.0.0"

# Qt's own translations (line edit context menus, standard dialog buttons) are
# collected by PyInstaller's Qt hook already: QtCore declares the "qtbase"
# catalogue and the hook globs every language of it into the bundle.  Naming
# the file here as well would mean hardcoding a path that moves between
# platforms -- the hook puts it under PySide6/Qt/translations everywhere except
# Windows, where it is PySide6/translations -- so leave the collection to it
# and let main.py look in both places.
datas = (
    collect_data_files("onnxruntime")
    + collect_data_files("mediapipe")
    + [
        ("assets/models/isnet-general-use.onnx", "assets/models"),
        ("assets/models/face_landmarker.task", "assets/models"),
        ("assets/models/blaze_face_short_range.tflite", "assets/models"),
        ("specs.json", "."),
        ("ui/icons", "ui/icons"),
    ]
)
binaries = collect_dynamic_libs("onnxruntime") + collect_dynamic_libs("mediapipe")
hiddenimports = [
    "numpy",
    "PIL",
    "onnxruntime",
]
# Matting runs onnxruntime directly, so rembg and its pymatting/numba/scipy
# dependency chain are no longer installed.  Excluding them keeps PyInstaller
# from pulling them back in through another package's optional import.
# matplotlib is deliberately absent from this list: mediapipe imports it at the
# top of its drawing utilities, so excluding it breaks face detection.
excludes = [
    "llvmlite",
    "numba",
    "pooch",
    "pymatting",
    "rembg",
    "scipy",
    "skimage",
]


a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="idphoto",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory="_internal",
    icon=windows_icon,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="idphoto",
)

# On macOS the COLLECT tree alone is not double-clickable; BUNDLE wraps it into
# a real .app.  NSHighResolutionCapable keeps the UI sharp on Retina displays,
# and NSRequiresAquaSystemAppearance=False lets the app follow dark mode.
#
# CFBundleLocalizations is what makes the native Finder open/save panel speak
# Chinese: macOS intersects this list with the user's AppleLanguages and hands
# the winner to AppKit.  Without it the panel falls back to English even on a
# Chinese system, which is why the same dialog is English when running from
# source -- there the bundle is the Python interpreter's, not ours.
#
# Chinese is listed alone on purpose.  Adding "en" would hand an English panel
# to anyone whose system is not Chinese, and the rest of this app has no
# English at all, so a German or Japanese user would get a Chinese window with
# an English file dialog bolted on.  With a single entry AppKit has nothing
# else to choose and every user gets the Chinese panel.
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="IDPhotoStudio.app",
        icon=mac_icon,
        bundle_identifier="com.adrianx1.idphotostudio",
        version=app_version,
        info_plist={
            "CFBundleName": "IDPhotoStudio",
            "CFBundleDisplayName": "IDPhotoStudio",
            "CFBundleShortVersionString": app_version,
            "CFBundleVersion": app_version,
            "CFBundleDevelopmentRegion": "zh_CN",
            "CFBundleLocalizations": ["zh_CN"],
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
