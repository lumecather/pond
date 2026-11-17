"""Pond as a desktop app.

Starts Django (on 127.0.0.1 only) and the trading bot, then opens a window with the interface.
The window is the system's built-in browser engine (Edge WebView2 on Windows) via pywebview.

    python desktop.py             open the app window
    python desktop.py --browser   open in your regular browser instead (if the window won't start)

Data lives in the user folder, see config/paths.py.
"""
import argparse
import logging
import os
import secrets
import sys
import threading
import time
import webbrowser
from pathlib import Path

from config.paths import APP_NAME, data_dir, secret_key

BOT_INTERVAL = 15       # how often the bot checks the rules, in seconds

log = logging.getLogger("pond")


def _setup_logging(folder: Path):
    # a windowed .exe has no stdout: anything printed goes to the log file instead
    log_file = folder / "pond.log"
    if sys.stdout is None or sys.stderr is None:
        stream = open(log_file, "a", encoding="utf-8", buffering=1)
        sys.stdout = sys.stdout or stream
        sys.stderr = sys.stderr or stream
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stderr)],
    )


def _single_instance(folder: Path):
    """Lock a file in the data folder while the app is open; a second launch can't get the lock.

    Two copies sharing one database would mean two bots executing the same rule twice.
    The OS releases the lock by itself if the app crashes.
    """
    handle = open(folder / "pond.lock", "a+")
    try:
        if sys.platform == "win32":
            import msvcrt

            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl

            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def prepare(folder: Path):
    os.environ.update({
        "POND_DATA": str(folder),
        "POND_TOKEN": secrets.token_urlsafe(32),
        "SECRET_KEY": secret_key(folder),
        "DJANGO_SETTINGS_MODULE": "config.settings",
    })
    import django
    from django.core.management import call_command

    django.setup()
    call_command("migrate", interactive=False, verbosity=0)
    # only the window of this launch may be logged in: drop sessions left over from earlier launches
    from django.contrib.sessions.models import Session

    Session.objects.all().delete()


def serve() -> int:
    from waitress.server import create_server

    from config.wsgi import application

    server = create_server(application, host="127.0.0.1", port=0, threads=8)
    threading.Thread(target=server.run, name="web", daemon=True).start()
    return server.effective_port


def bot_loop(stop: threading.Event):
    from django.db import close_old_connections

    from bot.services.engine import check_rules

    log.info("bot started, checking rules every %s s", BOT_INTERVAL)
    while not stop.wait(BOT_INTERVAL):
        try:
            close_old_connections()
            fired = check_rules()
            if fired:
                log.info("rules fired: %s", fired)
        except Exception:
            log.exception("bot pass failed")


def main():
    parser = argparse.ArgumentParser(description=f"{APP_NAME}: a trading bot that runs on your computer")
    parser.add_argument("--browser", action="store_true", help="open in your regular browser instead of the app window")
    parser.add_argument("--no-open", action="store_true", help="don't open anything, just print the address")
    args = parser.parse_args()

    folder = data_dir()
    _setup_logging(folder)
    lock = _single_instance(folder)
    try:
        import webview
    except Exception:
        webview = None

    if lock is None:
        text = f"{APP_NAME} is already running. Switch to the open window."
        log.warning(text)
        if webview and not args.browser:
            webview.create_window(APP_NAME, html=f"<p style='font:16px system-ui;padding:24px'>{text}</p>", width=420, height=160)
            webview.start()
        sys.exit(1)

    prepare(folder)
    port = serve()
    url = f"http://127.0.0.1:{port}/desktop/start/?token={os.environ['POND_TOKEN']}"
    stop = threading.Event()
    threading.Thread(target=bot_loop, args=(stop,), name="bot", daemon=True).start()
    log.info("%s started, data folder: %s", APP_NAME, folder)

    try:
        if webview and not args.browser and not args.no_open:
            webview.create_window(APP_NAME, url, width=1180, height=860, min_size=(380, 560))
            # private_mode=False: the window remembers small things like the chosen timeframe between launches
            webview.start(private_mode=False, storage_path=str(folder / "webview"))
        else:
            print(f"{APP_NAME} is running: {url}\nPress Ctrl+C to quit", flush=True)
            if not args.no_open:
                webbrowser.open(url)
            while True:
                time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        lock.close()


if __name__ == "__main__":
    main()
