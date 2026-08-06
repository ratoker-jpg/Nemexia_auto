# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

playwright_datas, playwright_binaries, playwright_hidden = collect_all('playwright')
bs4_datas, bs4_binaries, bs4_hidden = collect_all('bs4')
pystray_datas, pystray_binaries, pystray_hidden = collect_all('pystray')

analysis = Analysis(
    ['app.py'],
    pathex=[],
    binaries=playwright_binaries + bs4_binaries + pystray_binaries,
    datas=playwright_datas + bs4_datas + pystray_datas + [
        ('targets_seed.json', '.'),
        ('assets/nemexia.ico', 'assets'),
    ],
    hiddenimports=playwright_hidden + bs4_hidden + pystray_hidden + [
        'PIL._tkinter_finder', 'PIL.Image', 'PIL.ImageTk', 'soupsieve',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    analysis.binaries,
    analysis.datas,
    [],
    name='NemexiaRaidManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/nemexia.ico',
)
