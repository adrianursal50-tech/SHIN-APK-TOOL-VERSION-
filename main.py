#!/usr/bin/env python3
"""
SHIN · DRAKVEX — Kivy wrapper for Android.

Bundles DRAKVEX_ML.py and V2.py as importable modules and pipes stdin/stdout
through thread-safe queues so the touch UI can drive them. Source scripts are
NOT modified -- the wrapper monkeypatches the TTY assumptions (input(),
os.system('clear'), get_terminal_size, stdout, isatty).

Watermark layer: 140sp 'SHIN' rotated -28deg at 8% white alpha, plus a
bottom-right 'SHIN · DRAKVEX' signature.
"""

import os, sys, io, re, queue, threading, builtins, importlib.util, traceback
from pathlib import Path

os.environ.setdefault('KIVY_NO_CONSOLELOG', '1')
os.environ.setdefault('KIVY_NO_ARGS', '1')

from kivy.app import App
from kivy.clock import Clock
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.scrollview import ScrollView
from kivy.uix.spinner import Spinner
from kivy.uix.textinput import TextInput
from kivy.graphics import PushMatrix, PopMatrix, Rotate

# ------------------------------------------------------------------ #
# ANSI strip -- Kivy TextInput cannot render escape sequences.
# ------------------------------------------------------------------ #
_ANSI_RE = re.compile(
    r'\x1b\[[0-9;?]*[A-Za-z]'
    r'|\x1b\][^\x07]*\x07'
    r'|\x1b[()][AB012]'
)

def _strip_ansi(s: str) -> str:
    return _ANSI_RE.sub('', s)


# ------------------------------------------------------------------ #
# Stream + queue plumbing
# ------------------------------------------------------------------ #
_out_q: "queue.Queue[tuple[str, str]]" = queue.Queue()
_in_q:  "queue.Queue[str | None]"      = queue.Queue()
_stop_flag = threading.Event()
_run_thread: threading.Thread | None = None
_MAX_CHARS = 400_000


class _QueueStream(io.TextIOBase):
    def __init__(self, is_err: bool = False):
        self.is_err = is_err
    def write(self, s):
        if not s:
            return 0
        s = _strip_ansi(s).replace('\r\n', '\n').replace('\r', '\n')
        if s:
            _out_q.put(('err' if self.is_err else 'out', s))
        return len(s)
    def flush(self): pass
    def isatty(self): return True
    def writable(self): return True
    def readable(self): return False
    def fileno(self): raise io.UnsupportedOperation('fileno')
    @property
    def encoding(self): return 'utf-8'


# ------------------------------------------------------------------ #
# Monkeypatches -- installed before scripts are imported
# ------------------------------------------------------------------ #
def _kivy_input(prompt=''):
    if prompt:
        _out_q.put(('out', str(prompt)))
    _out_q.put(('out', '\n'))
    if _stop_flag.is_set():
        raise KeyboardInterrupt('stopped')
    val = _in_q.get()
    if val is None:
        raise KeyboardInterrupt('stopped')
    return val

builtins.input = _kivy_input

_orig_system = os.system
def _kivy_system(cmd):
    if isinstance(cmd, str) and ('clear' in cmd or cmd.strip().startswith('cls')):
        _out_q.put(('clear', ''))
        return 0
    return _orig_system(cmd)

os.system = _kivy_system

import shutil as _shutil
def _fake_term_size(fallback=(80, 30)):
    try:
        return os.terminal_size((80, 30))
    except Exception:
        return fallback

_shutil.get_terminal_size = _fake_term_size


# ------------------------------------------------------------------ #
# Script runner
# ------------------------------------------------------------------ #
APP_DIR = Path(__file__).resolve().parent
SCRIPTS = {
    'DRAKVEX_ML': APP_DIR / 'DRAKVEX_ML.py',
    'V2':         APP_DIR / 'V2.py',
}

def _pick_entry(mod, name):
    if name == 'DRAKVEX_ML' and hasattr(mod, 'main'):
        return mod.main
    if name == 'V2' and hasattr(mod, 'run_bruteforce_login'):
        return mod.run_bruteforce_login
    for cand in ('main', 'run_bruteforce_login', 'run'):
        if hasattr(mod, cand):
            return getattr(mod, cand)
    return None

def _run_script(name: str):
    path = SCRIPTS.get(name)
    if path is None or not path.exists():
        _out_q.put(('err', f'\n[SHIN] script not found: {path}\n'))
        return

    mod_name = f'_wrapped_{name}'
    try:
        spec = importlib.util.spec_from_file_location(mod_name, str(path))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[mod_name] = mod
        spec.loader.exec_module(mod)
    except SystemExit:
        pass
    except Exception:
        _out_q.put(('err', '\n[SHIN] import failed:\n' + traceback.format_exc()))
        return

    entry = _pick_entry(mod, name)
    if entry is None:
        _out_q.put(('err', f'\n[SHIN] no entry point in {name}\n'))
        return

    try:
        entry()
    except KeyboardInterrupt:
        _out_q.put(('out', '\n[SHIN] interrupted\n'))
    except SystemExit:
        pass
    except Exception:
        _out_q.put(('err', '\n[SHIN] runtime error:\n' + traceback.format_exc()))


# ------------------------------------------------------------------ #
# UI
# ------------------------------------------------------------------ #
class Root(BoxLayout):
    def __init__(self, **kw):
        super().__init__(orientation='vertical',
                         padding=dp(6), spacing=dp(6), **kw)
        self._build()

    def _build(self):
        # --- top bar ---
        top = BoxLayout(size_hint_y=None, height=dp(46), spacing=dp(6))
        chip = Label(
            text='SHIN',
            size_hint=(None, 1),
            width=dp(64),
            bold=True,
            font_size=dp(13),
            color=(1.0, 0.878, 0.698, 1),
        )
        # chip background via canvas
        from kivy.graphics import Color, Rectangle
        with chip.canvas.before:
            Color(0.784, 0.078, 0.078, 1)   # #C81414
            chip._bg = Rectangle(pos=chip.pos, size=chip.size)
        chip.bind(pos=lambda *a: setattr(chip._bg, 'pos', chip.pos),
                  size=lambda *a: setattr(chip._bg, 'size', chip.size))

        self.spinner = Spinner(
            text='DRAKVEX_ML',
            values=('DRAKVEX_ML', 'V2'),
            size_hint=(1, 1),
        )
        start = Button(text='START', size_hint=(None, 1), width=dp(80),
                       color=(0.043, 0.855, 0.318, 1))
        start.bind(on_release=self._start)
        stop = Button(text='STOP', size_hint=(None, 1), width=dp(72),
                      color=(1.0, 0.231, 0.231, 1))
        stop.bind(on_release=self._stop)
        top.add_widget(chip)
        top.add_widget(self.spinner)
        top.add_widget(start)
        top.add_widget(stop)

        # --- output ---
        self.out = TextInput(
            readonly=True,
            multiline=True,
            font_size=dp(11),
            background_color=(0.04, 0.04, 0.04, 1),
            foreground_color=(0.87, 0.87, 0.87, 1),
            cursor_color=(0, 0, 0, 0),
        )
        scroll = ScrollView()
        scroll.add_widget(self.out)
        self._scroll = scroll

        # --- input row ---
        bottom = BoxLayout(size_hint_y=None, height=dp(44), spacing=dp(6))
        self.inp = TextInput(
            multiline=False,
            font_size=dp(13),
            hint_text='type input, tap SEND',
            size_hint=(0.74, 1),
        )
        self.inp.bind(on_text_validate=self._send)
        send = Button(text='SEND', size_hint=(0.26, 1),
                      color=(0.784, 0.078, 0.078, 1))
        send.bind(on_release=self._send)
        bottom.add_widget(self.inp)
        bottom.add_widget(send)

        self.add_widget(top)
        self.add_widget(scroll)
        self.add_widget(bottom)

        # --- watermark layers (added last = drawn on top) ---
        self._add_watermark()
        self._add_signature()

        Clock.schedule_interval(self._drain, 1 / 30)

    def _add_watermark(self):
        wm = Label(
            text='SHIN',
            font_size=dp(150),
            bold=True,
            color=(1, 1, 1, 0.08),
            size_hint=(None, None),
            size=(Window.width * 1.8, Window.height * 0.6),
            pos=(-Window.width * 0.4, Window.height * 0.2),
        )
        with wm.canvas.before:
            PushMatrix()
            Rotate(angle=-28, origin=wm.center)
        with wm.canvas.after:
            PopMatrix()
        self.add_widget(wm)

    def _add_signature(self):
        sig = Label(
            text='SHIN · DRAKVEX',
            font_size=dp(9),
            color=(1, 0.42, 0.17, 0.4),
            size_hint=(None, None),
            size=(dp(160), dp(20)),
            pos=(Window.width - dp(165), dp(6)),
            halign='right',
        )
        self.add_widget(sig)

    # ---------------- output pump ---------------- #
    def _drain(self, _dt):
        dirty = False
        try:
            while True:
                kind, text = _out_q.get_nowait()
                if kind == 'clear':
                    self.out.text = ''
                else:
                    self.out.text += text
                dirty = True
        except queue.Empty:
            pass
        if dirty:
            if len(self.out.text) > _MAX_CHARS:
                cut = len(self.out.text) - _MAX_CHARS // 2
                nl = self.out.text.find('\n', cut)
                self.out.text = self.out.text[nl + 1:] if nl > 0 else self.out.text[-_MAX_CHARS // 2:]
            self.out.cursor = (0, len(self.out.text))
            self._scroll.scroll_y = 0
        return True

    # ---------------- input ---------------- #
    def _send(self, *_):
        txt = self.inp.text
        self.inp.text = ''
        _out_q.put(('out', txt + '\n'))
        _in_q.put(txt)

    # ---------------- lifecycle ---------------- #
    def _start(self, *_):
        global _run_thread
        if _run_thread and _run_thread.is_alive():
            _out_q.put(('out', '\n[SHIN] already running -- STOP first\n'))
            return
        _stop_flag.clear()
        while not _in_q.empty():
            try:
                _in_q.get_nowait()
            except queue.Empty:
                break
        name = self.spinner.text
        _out_q.put(('out', f'\n[SHIN] launching {name}...\n'))
        _run_thread = threading.Thread(target=_run_script,
                                       args=(name,), daemon=True)
        _run_thread.start()

    def _stop(self, *_):
        _stop_flag.set()
        try:
            _in_q.put(None)
        except Exception:
            pass
        _out_q.put(('out', '\n[SHIN] stop requested\n'))


class ShinApp(App):
    def build(self):
        Window.clearcolor = (0.02, 0.02, 0.02, 1)
        self.title = 'SHIN'
        return Root()


if __name__ == '__main__':
    sys.stdout = _QueueStream(False)
    sys.stderr = _QueueStream(True)
    _out_q.put(('out',
        '==============================================\n'
        '  SHIN  ·  SHIN on-device build\n'
        '  watermark: SHIN  ·  package: com.shin.shindrakvex\n'
        '==============================================\n\n'
    ))
    ShinApp().run()
