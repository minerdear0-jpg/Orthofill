"""Окно Orthofill: tkinter + тема sv-ttk (в стиле Windows 11)."""
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import VERSION_LABEL
from .controller import Controller, layout_mode
from .journal import DB_NAME, Journal, data_dir

TITLE = f'Orthofill {VERSION_LABEL}'
REMINDER = 'Проверьте протокол перед вставкой в служебное ПО'
DISCLAIMER = 'Программа формирует черновик протокола; ответственность за содержание несёт врач.'

ACCENT = '#1f5f8b'
BADGE_BG, BADGE_FG = '#f0b429', '#3b2a00'
WARN_BG, WARN_FG, WARN_BORDER = '#fff7e0', '#6b4e00', '#f0d58a'
WARN_TEXT = '#b04a00'
MUTED = '#6b7a89'

# Сочетания клавиш по физической клавише: в русской раскладке Tk не узнаёт
# Ctrl+C/V/X/A/Z и Ctrl+O. Windows: virtual-key коды; X11: keycode.
_VK = {67: 'c', 86: 'v', 88: 'x', 65: 'a', 90: 'z', 79: 'o'}
_X11 = {54: 'c', 55: 'v', 53: 'x', 38: 'a', 52: 'z', 32: 'o'}


def _resource(name: str) -> Path:
    base = Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))
    return base / name


def _set_dpi_aware() -> None:
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass


class App:
    def __init__(self, root: tk.Tk, controller: Controller):
        self.root, self.ctl = root, controller
        self.mode: str | None = None
        self._setup_fonts()
        self._build()
        self._bind_keys()
        self.ctl.startup()
        self.diag_var.set(self.ctl.diagnostics)
        self._show_diag()
        self._show_file_status()
        self.raw_txt.focus_set()

    # ---------- построение ----------
    def _setup_fonts(self):
        fam = 'Segoe UI' if 'Segoe UI' in tkfont.families() else tkfont.nametofont('TkDefaultFont').actual('family')
        for name in ('TkDefaultFont', 'TkTextFont', 'TkMenuFont', 'TkHeadingFont'):
            tkfont.nametofont(name).configure(family=fam, size=10)
        self.f_text = tkfont.Font(family=fam, size=11)
        self.f_title = tkfont.Font(family=fam, size=13, weight='bold')
        self.f_small = tkfont.Font(family=fam, size=9)
        self.f_label = tkfont.Font(family=fam, size=9, weight='bold')

    def _text(self, parent, height):
        frame = ttk.Frame(parent, style='Card.TFrame', padding=1)
        txt = tk.Text(frame, height=height, wrap='word', font=self.f_text, undo=True,
                      relief='flat', borderwidth=0, padx=8, pady=6,
                      background='#ffffff', foreground='#1f2a37', insertbackground='#1f2a37',
                      highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient='vertical', command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        return frame, txt

    def _build(self):
        r = self.root
        r.title(TITLE)
        r.minsize(420, 520)

        # Шапка
        head = tk.Frame(r, bg=ACCENT, padx=14, pady=8)
        head.pack(fill='x')
        tk.Label(head, text='Orthofill', bg=ACCENT, fg='white', font=self.f_title).pack(side='left')
        tk.Label(head, text=VERSION_LABEL, bg=BADGE_BG, fg=BADGE_FG, font=self.f_small,
                 padx=6).pack(side='left', padx=(8, 0))
        about = tk.Label(head, text='О программе', bg=ACCENT, fg='white', cursor='hand2',
                         font=tkfont.Font(family=self.f_small.actual('family'), size=9,
                                          underline=True))
        about.pack(side='right')
        about.bind('<Button-1>', lambda e: self.about())
        self.head_lbl = tk.Label(head, text='', bg=ACCENT, font=self.f_small, padx=12)
        self.head_lbl.pack(side='right')

        # Строка файла
        self.bar = bar = ttk.Frame(r, padding=(12, 8, 12, 4))
        bar.pack(fill='x')
        self.bar_left = left = ttk.Frame(bar)
        ttk.Button(left, text='Открыть файл…', command=self.open_file).pack(side='left')
        self.file_lbl = ttk.Label(left, text='', padding=(10, 0))
        self.file_lbl.pack(side='left')
        self.bar_right = right = ttk.Frame(bar)
        self.details_btn = ttk.Button(right, text='Подробнее', command=self.show_details)
        self.topmost = tk.BooleanVar(value=self.ctl.journal.get_setting('topmost') == '1')
        topmost_cb = ttk.Checkbutton(right, text='Поверх окон', variable=self.topmost,
                                     command=self._apply_topmost)
        self.diag_var = tk.BooleanVar(value=False)
        diag_cb = ttk.Checkbutton(right, text='Диагностика', variable=self.diag_var,
                                  command=self._toggle_diag)
        self.diag_btn = ttk.Button(right, text='Папка', command=self.open_diag_folder)
        # широко — в ряд; узко — сеткой 2×2 (см. _relayout)
        self.bar_widgets = [self.details_btn, topmost_cb, diag_cb, self.diag_btn]
        self._apply_topmost()

        # Ввод и протокол
        self.body = ttk.Frame(r, padding=(12, 4, 12, 4))

        self.in_panel = ttk.Frame(self.body)
        ttk.Label(self.in_panel, text='КРАТКАЯ ЗАПИСЬ ВРАЧА', font=self.f_label,
                  foreground=MUTED).pack(anchor='w', pady=(0, 3))
        # кнопки пакуются раньше текста: при нехватке места сжимается текст
        row = ttk.Frame(self.in_panel)
        row.pack(side='bottom', fill='x', pady=(8, 0))
        ttk.Button(row, text='Сформировать и копировать', style='Accent.TButton',
                   command=self.generate).pack(side='left')
        ttk.Label(row, text='Ctrl+Enter', foreground=MUTED, padding=(8, 0)).pack(side='left')
        f, self.raw_txt = self._text(self.in_panel, 3)
        f.pack(fill='both', expand=True)

        self.out_panel = ttk.Frame(self.body)
        ttk.Label(self.out_panel, text='ПРОТОКОЛ (МОЖНО ПРАВИТЬ)', font=self.f_label,
                  foreground=MUTED).pack(anchor='w', pady=(0, 3))
        row = ttk.Frame(self.out_panel)
        row.pack(side='bottom', fill='x', pady=(8, 0))
        ttk.Button(row, text='Копировать', command=self.copy).pack(side='left')
        ttk.Button(row, text='Сохранить как эталон',
                   command=self.save_reference).pack(side='left', padx=8)
        tk.Label(self.out_panel, text=f'⚠  {REMINDER}', bg=WARN_BG, fg=WARN_FG,
                 highlightbackground=WARN_BORDER, highlightthickness=1, anchor='w',
                 justify='left', padx=8, pady=4).pack(side='bottom', fill='x', pady=(6, 0))
        f, self.out_txt = self._text(self.out_panel, 6)
        f.pack(fill='both', expand=True)

        # Строка статуса
        st = ttk.Frame(r, padding=(12, 4, 12, 8))
        st.pack(fill='x', side='bottom')
        self.body.pack(fill='both', expand=True)   # после статуса: сжимается тело, а не статус
        self.status_lbl = ttk.Label(st, text='')
        self.status_lbl.pack(anchor='w')
        self.warn_lbl = ttk.Label(st, text='', foreground=WARN_TEXT, justify='left')
        self.warn_lbl.pack(anchor='w')
        self.def_lbl = ttk.Label(st, text='', foreground=MUTED, justify='left')
        self.def_lbl.pack(anchor='w')
        st.bind('<Configure>', lambda e: [w.configure(wraplength=max(200, e.width - 30))
                                          for w in (self.warn_lbl, self.def_lbl)])

        r.bind('<Configure>', self._on_resize)
        self._relayout('wide')

    def _relayout(self, mode: str):
        if mode == self.mode:
            return
        self.mode = mode
        for p in (self.in_panel, self.out_panel):
            p.grid_forget()
        self.bar_left.pack_forget()
        self.bar_right.pack_forget()
        for w in self.bar_widgets:
            w.grid_forget()
        if mode == 'wide':
            self.bar_left.pack(side='left')
            self.bar_right.pack(side='right')
            for i, w in enumerate(self.bar_widgets):
                w.grid(row=0, column=i, padx=(8, 0))
        else:   # узко: кнопки окна — второй строкой, сеткой 2×2
            self.bar_left.pack(anchor='w')
            self.bar_right.pack(anchor='w', pady=(6, 0))
            for i, w in enumerate(self.bar_widgets):
                w.grid(row=i % 2, column=i // 2, sticky='w', padx=(0, 12), pady=2)
        b = self.body
        for i in range(2):
            b.columnconfigure(i, weight=0)
            b.rowconfigure(i, weight=0)
        if mode == 'wide':
            self.in_panel.grid(row=0, column=0, sticky='nsew', padx=(0, 12))
            self.out_panel.grid(row=0, column=1, sticky='nsew')
            b.columnconfigure(0, weight=2)
            b.columnconfigure(1, weight=3)
            b.rowconfigure(0, weight=1)
        else:
            self.in_panel.grid(row=0, column=0, sticky='nsew', pady=(0, 10))
            self.out_panel.grid(row=1, column=0, sticky='nsew')
            b.columnconfigure(0, weight=1)
            b.rowconfigure(0, weight=1)
            b.rowconfigure(1, weight=3)

    def _on_resize(self, e):
        if e.widget is self.root:
            scale = self.root.winfo_fpixels('1i') / 96
            self._relayout(layout_mode(int(e.width / scale)))
            self.file_lbl.configure(wraplength=0 if self.mode == 'wide' else max(150, e.width - 220))

    # ---------- клавиши ----------
    def _bind_keys(self):
        for w in (self.raw_txt, self.out_txt):
            for seq in ('<Control-Return>', '<Control-KP_Enter>'):
                w.bind(seq, lambda e: (self.generate(), 'break')[1])
        self.root.bind_all('<Control-KeyPress>', self._on_ctrl_key, add='+')

    def _on_ctrl_key(self, e):
        latin = len(e.keysym) == 1 and e.keysym.isascii()
        key = (_VK if sys.platform == 'win32' else _X11).get(e.keycode)
        shift = bool(e.state & 0x1)
        if key == 'c' and shift:
            self.copy()
            return 'break'
        if key == 'o':
            self.open_file()
            return 'break'
        if latin or key is None:
            return None          # обычная раскладка — работает штатная привязка
        w = e.widget
        if isinstance(w, (tk.Text, tk.Entry, ttk.Entry)):
            if key == 'a' and isinstance(w, tk.Text):
                w.tag_add('sel', '1.0', 'end-1c')
            elif key in ('c', 'v', 'x', 'z'):
                w.event_generate({'c': '<<Copy>>', 'v': '<<Paste>>',
                                  'x': '<<Cut>>', 'z': '<<Undo>>'}[key])
            return 'break'
        return None

    # ---------- действия ----------
    def _clipboard(self, text: str):
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        self.root.update()

    def _status(self, text: str, warnings=(), defaults_line: str = ''):
        self.status_lbl.configure(text=text)
        self.warn_lbl.configure(text='\n'.join(f'⚠ {w}' for w in warnings))
        self.def_lbl.configure(text=defaults_line)

    def _show_file_status(self):
        s = self.ctl.file_status
        self.file_lbl.configure(text=f'{self._file_name()}   {s}',
                                foreground='#1f7a3f' if s.startswith('✓') else
                                WARN_TEXT if s.startswith(('⚠', '✗', 'Файл не найден')) else MUTED)
        if self.ctl.details:
            self.details_btn.state(['!disabled'])
        else:
            self.details_btn.state(['disabled'])

    def _file_name(self) -> str:
        wb = self.ctl.workbook
        return f'📄 {wb.path.name}' if wb else ''

    def open_file(self):
        p = filedialog.askopenfilename(title='Файл классификатора',
                                       filetypes=[('Excel', '*.xlsx'), ('Все файлы', '*.*')])
        if p:
            self.ctl.open_file(Path(p))
            self._show_file_status()
            if self.ctl.details and not self.ctl.file_status.startswith('✓'):
                self.show_details()

    def generate(self):
        current = self.out_txt.get('1.0', 'end-1c')
        if self.ctl.needs_confirm_regenerate(current) and not messagebox.askyesno(
                TITLE, 'Заменить исправленный протокол новым?', icon='warning'):
            return
        r = self.ctl.generate(self.raw_txt.get('1.0', 'end-1c'))
        if r.copied:
            self.out_txt.delete('1.0', 'end')
            self.out_txt.insert('1.0', r.text)
            self.out_txt.edit_reset()
        self._status(r.status, r.warnings, r.defaults_line)

    def copy(self):
        text = self.out_txt.get('1.0', 'end-1c').strip()
        if text:
            self._status(self.ctl.copy(text))

    def save_reference(self):
        raw = self.raw_txt.get('1.0', 'end-1c').strip()
        text = self.out_txt.get('1.0', 'end-1c').strip()
        wb = self.ctl.workbook
        if not (raw and text and wb):
            self._status('Сначала сформируйте протокол')
            return
        if messagebox.askyesno(TITLE, f'Сохранить запись и протокол как эталон в файл\n'
                                      f'{wb.path.name}?\n\nЗапись: {raw[:200]}'):
            self._status(self.ctl.save_reference(raw, text))
            self._show_file_status()

    def show_details(self):
        win = tk.Toplevel(self.root)
        win.title(f'{TITLE} — проверка файла')
        win.geometry('760x480')
        ttk.Label(win, text=self.ctl.file_status, padding=10).pack(anchor='w')
        f, txt = self._text(win, 20)
        f.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        txt.insert('1.0', '\n'.join(self.ctl.details) or 'Замечаний нет.')
        txt.configure(state='disabled')

    def about(self):
        wb = self.ctl.workbook
        messagebox.showinfo(TITLE, f'{TITLE}\n\n{DISCLAIMER}\n\n'
                                   f'Файл классификатора:\n{wb.path if wb else "не открыт"}\n\n'
                                   f'Журнал:\n{self.ctl.journal.db_path}\n\n'
                                   f'Диагностика ({"включена" if self.ctl.diagnostics else "выключена"}):\n'
                                   f'{self.ctl.diag_dir}')

    def _toggle_diag(self):
        self.ctl.set_diagnostics(self.diag_var.get())
        self._show_diag()
        if self.ctl.diagnostics:
            self._status(f'Диагностика включена: {self.ctl.diag_dir}')
        else:
            self._status('Диагностика выключена')

    def _show_diag(self):
        on = self.ctl.diagnostics
        self.head_lbl.configure(text='● Диагностика включена' if on else 'Протокол активации',
                                fg=BADGE_BG if on else '#d7e6f2')
        self.diag_btn.state(['!disabled'] if on or self.ctl.diag_dir.exists() else ['disabled'])

    def open_diag_folder(self):
        d = self.ctl.diag_dir
        d.mkdir(parents=True, exist_ok=True)
        if sys.platform == 'win32':
            import os
            os.startfile(d)
        else:
            import subprocess
            subprocess.Popen(['xdg-open', str(d)])

    def _apply_topmost(self):
        self.root.attributes('-topmost', self.topmost.get())

    def close(self):
        j = self.ctl.journal
        j.set_setting('geometry', self.root.geometry())
        j.set_setting('topmost', '1' if self.topmost.get() else '0')
        self.root.destroy()


def run() -> None:
    _set_dpi_aware()
    root = tk.Tk()
    try:
        import sv_ttk
        sv_ttk.set_theme('light')
    except Exception:
        pass
    root.configure(background=ttk.Style().lookup('TFrame', 'background') or '#fafafa')
    ico = _resource('assets/orthofill.ico')
    if sys.platform == 'win32' and ico.exists():
        root.iconbitmap(default=str(ico))
    journal = Journal(data_dir() / DB_NAME)
    root.geometry(journal.get_setting('geometry') or '1100x720')
    app = App(root, Controller(journal, clipboard=lambda t: None))
    app.ctl.clipboard = app._clipboard
    root.protocol('WM_DELETE_WINDOW', app.close)

    def on_error(exc, val, tb):   # в exe без консоли иначе ошибку никто не увидит
        import traceback
        messagebox.showerror(TITLE, f'Ошибка: {val}')
        try:
            (journal.db_path.parent / 'orthofill-errors.log').open('a', encoding='utf-8').write(
                ''.join(traceback.format_exception(exc, val, tb)) + '\n')
        except OSError:
            pass
    root.report_callback_exception = on_error
    root.mainloop()


def selftest() -> int:
    """Окно с темой создаётся и закрывается; 0 — всё на месте."""
    try:
        root = tk.Tk()
        import sv_ttk
        sv_ttk.set_theme('light')
        ttk.Button(root, text='Проверка', style='Accent.TButton').pack()
        root.update()
        root.destroy()
        return 0
    except Exception as e:
        print(f'selftest-ui: {e}', file=sys.stderr)
        return 1
