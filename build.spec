# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, copy_metadata


# Platform icons are optional: a missing file must not break the build, since
# `python -m PyInstaller build.spec` also runs on developer machines that have
# not generated them yet.
def _icon(name: str) -> str | None:
    path = Path("assets") / name
    return str(path) if path.is_file() else None


mac_icon = _icon("icon.icns")
windows_icon = _icon("icon.ico")

datas = (
    collect_data_files("onnxruntime")
    + collect_data_files("mediapipe")
    + copy_metadata("pymatting")
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
    "scipy",
    "scipy.ndimage",
    "skimage",
    "skimage.morphology",
    "pymatting",
    "pymatting.alpha",
    "pymatting.foreground",
    "pymatting.util",
    "tqdm",
    "pooch",
    "jsonschema",
    "onnxruntime",
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
    excludes=[],
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
if sys.platform == "darwin":
    app = BUNDLE(
        coll,
        name="IDPhotoStudio.app",
        icon=mac_icon,
        bundle_identifier="com.adrianx1.idphotostudio",
        info_plist={
            "CFBundleName": "IDPhotoStudio",
            "CFBundleDisplayName": "IDPhotoStudio",
            "NSHighResolutionCapable": True,
            "NSRequiresAquaSystemAppearance": False,
        },
    )
