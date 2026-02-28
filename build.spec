# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

import sys
import os
from PyQt5.QtCore import QLibraryInfo

# 获取 PyQt5 插件路径
qt_plugins_path = QLibraryInfo.location(QLibraryInfo.PluginsPath)

# 收集 imageformats 插件
imageformats_path = os.path.join(qt_plugins_path, 'imageformats')
imageformats_binaries = []
if os.path.exists(imageformats_path):
    for dll in os.listdir(imageformats_path):
        if dll.endswith('.dll'):
            imageformats_binaries.append(
                (os.path.join(imageformats_path, dll), 'PyQt5/Qt/plugins/imageformats')
            )

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=imageformats_binaries,
    datas=[('resources/sm.txt', 'resources')],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'cryptography',
        'cryptography.fernet',
        'PIL',
        'PIL.Image',
        'requests',
        'urllib3',
        'google.generativeai',
        'cv2',
        'numpy',
        'jwt',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='TapNow',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
