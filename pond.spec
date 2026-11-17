# PyInstaller: builds the app into dist/Pond (Pond.exe inside).
# Build with build_exe.bat (Windows) or:  python -m PyInstaller --noconfirm pond.spec
import os

from PyInstaller.utils.hooks import collect_all, collect_submodules

# PyInstaller imports the Django settings to find modules. These values only exist during the build:
# they don't end up in the .exe; the app creates real ones in its data folder on first launch.
os.environ.update({"DJANGO_SETTINGS_MODULE": "config.settings", "SECRET_KEY": "build-only", "POND_DATA": os.path.abspath("build/pond-data")})

datas = [("templates", "templates"), ("static", "static")]
binaries, hiddenimports = [], []

# libraries with data files and dynamic imports: take them whole
for package in ("django", "web3", "eth_account", "eth_abi", "eth_keys", "eth_utils", "eth_hash", "eth_typing",
                "hexbytes", "ckzg", "markdown", "waitress", "webview", "tzlocal", "tzdata"):
    try:
        d, b, h = collect_all(package)
    except Exception:
        continue
    datas += d
    binaries += b
    hiddenimports += h

# our code and Django migrations are loaded by name, so PyInstaller won't find them on its own
for app in ("config", "users", "bot", "guides"):
    hiddenimports += collect_submodules(app, filter=lambda name: ".tests" not in name)

a = Analysis(
    ["desktop.py"],
    pathex=["."],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports,
    # tests and dev tools stay out of the app
    excludes=["tkinter", "eth_tester", "pytest", "IPython", "bot.tests",
              "pkg_resources", "setuptools"],  # the app doesn't need pkg_resources, and it breaks at startup
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Pond",
    console=False,               # no console window; the log goes to pond.log in the data folder
    icon="static/img/pond.ico",
)
coll = COLLECT(exe, a.binaries, a.datas, name="Pond")
