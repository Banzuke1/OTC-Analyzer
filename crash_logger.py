"""
Egyszerű összeomlás-naplózó, adb/logcat nélkül is használható.
Minden elkapott kivételt egy fájlba ment (user_data_dir/crash.log).
A következő appindításkor a main.py kiolvassa és megjeleníti, hogy
screenshotolható legyen.
"""
import os, sys, threading, traceback

_LOG_PATH = None

def _get_path():
    global _LOG_PATH
    if _LOG_PATH is None:
        try:
            from kivy.app import App
            _LOG_PATH = os.path.join(App.get_running_app().user_data_dir, "crash.log")
        except Exception:
            _LOG_PATH = os.path.join(os.path.dirname(__file__), "crash.log")
    return _LOG_PATH

def _write(text):
    try:
        with open(_get_path(), "a", encoding="utf-8") as f:
            f.write(text + "\n\n")
    except Exception:
        pass

def log_exception(context=""):
    _write(f"--- {context} ---\n" + traceback.format_exc())

def install():
    def excepthook(exc_type, exc_value, exc_tb):
        _write("--- MAIN THREAD CRASH ---\n" +
               "".join(traceback.format_exception(exc_type, exc_value, exc_tb)))
        sys.__excepthook__(exc_type, exc_value, exc_tb)
    sys.excepthook = excepthook

    def thread_hook(args):
        _write(f"--- THREAD CRASH ({args.thread.name}) ---\n" +
               "".join(traceback.format_exception(args.exc_type, args.exc_value, args.exc_traceback)))
    threading.excepthook = thread_hook

def read_and_clear():
    path = _get_path()
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                content = f.read()
            os.remove(path)
            return content
        except Exception:
            return None
    return None
