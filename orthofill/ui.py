"""Окно Orthofill: tkinter + тема sv-ttk (в стиле Windows 11)."""
from __future__ import annotations

import re
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, font as tkfont, messagebox, ttk

from . import VERSION_LABEL
from .controller import CASE_KINDS, Controller, layout_mode
from .journal import DB_NAME, Journal, data_dir

TITLE = f'Orthofill {VERSION_LABEL}'


def window_title() -> str:
    """Версия и код сборки — сразу видно, какой код запущен."""
    from .buildinfo import build_id
    return f'{TITLE} · сборка {build_id()}'
CHANGELOG = 'CHANGELOG.md'
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
        if self.ctl.whats_new_pending():
            self.news_lbl.pack(side='left')
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
        r.title(window_title())
        r.minsize(420, 520)

        # Шапка
        head = tk.Frame(r, bg=ACCENT, padx=14, pady=8)
        head.pack(fill='x')
        tk.Label(head, text='Orthofill', bg=ACCENT, fg='white', font=self.f_title).pack(side='left')
        tk.Label(head, text=VERSION_LABEL, bg=BADGE_BG, fg=BADGE_FG, font=self.f_small,
                 padx=6).pack(side='left', padx=(8, 0))
        # имя пресета крупно — чтобы не перепутать тип карточки
        self.head_preset = tk.Label(head, text='', bg=ACCENT, fg='white', font=self.f_title)
        self.head_preset.pack(side='left', padx=(14, 0))
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
        self.preset_btn = ttk.Menubutton(left, text='Пресет')
        self.preset_menu = tk.Menu(self.preset_btn, tearoff=False)
        self.preset_btn['menu'] = self.preset_menu
        self.preset_btn.pack(side='left')
        self.preset_var = tk.IntVar(value=-1)
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
        # непонятые программой слова — подчёркнуты; нажатие — «добавить для слова»
        self.raw_txt.tag_configure('unknown', underline=1, foreground=WARN_TEXT)
        self.raw_txt.tag_configure('learned', underline=1, foreground='#1f7a3f')
        self.raw_txt.tag_bind('unknown', '<Enter>', lambda e: (
            self.raw_txt.configure(cursor='hand2'),
            self.status_lbl.configure(text='Программа не поняла это слово — нажмите, '
                                           'чтобы выбрать пункт')))
        self.raw_txt.tag_bind('unknown', '<Leave>', lambda e: self.raw_txt.configure(cursor='xterm'))
        self.raw_txt.tag_bind('unknown', '<Button-1>', self._on_unknown_click)
        self.raw_txt.bind('<KeyRelease>', self._unmark_unknown, add='+')
        f.pack(fill='both', expand=True)

        self.out_panel = ttk.Frame(self.body)
        ttk.Label(self.out_panel, text='ПРОТОКОЛ (МОЖНО ПРАВИТЬ)', font=self.f_label,
                  foreground=MUTED).pack(anchor='w', pady=(0, 3))
        # «Добавить пункт»: поиск по пресету, список — в той же панели (без всплывающих окон)
        self.add_box = ttk.Frame(self.out_panel)
        self.add_box.pack(fill='x', pady=(0, 4))
        self.add_for = ttk.Frame(self.add_box)
        self.add_for_lbl = ttk.Label(self.add_for, text='', foreground=WARN_TEXT)
        self.add_for_lbl.pack(side='left')
        ttk.Button(self.add_for, text='×', width=2,
                   command=self._close_add).pack(side='left', padx=(6, 0))
        row_add = ttk.Frame(self.add_box)
        row_add.pack(fill='x')
        ttk.Label(row_add, text='+ Добавить пункт:', foreground=MUTED).pack(side='left')
        self.add_entry = ttk.Entry(row_add)
        self.add_entry.pack(side='left', fill='x', expand=True, padx=(6, 0))
        self.add_list = tk.Listbox(self.add_box, height=7, activestyle='dotbox',
                                   font=self.f_small, exportselection=False)
        self._hits = []
        self._add_word: str | None = None
        self.add_entry.bind('<KeyRelease>', self._on_add_key)
        self.add_entry.bind('<Down>', lambda e: (self._move_hit(1), 'break')[1])
        self.add_entry.bind('<Up>', lambda e: (self._move_hit(-1), 'break')[1])
        self.add_entry.bind('<Return>', lambda e: (self._add_selected(None), 'break')[1])
        self.add_entry.bind('<Escape>', lambda e: (self._close_add(), 'break')[1])
        self.add_list.bind('<ButtonRelease-1>', lambda e: self._add_selected(None))
        row = ttk.Frame(self.out_panel)
        row.pack(side='bottom', fill='x', pady=(8, 0))
        self.out_row = row
        self.out_btns = [
            ttk.Button(row, text='Копировать', command=self.copy),
            ttk.Button(row, text='Отметить ошибку', command=self.mark_case),
            ttk.Button(row, text='Сохранить как эталон', command=self.save_reference),
        ]
        tk.Label(self.out_panel, text=f'⚠  {REMINDER}', bg=WARN_BG, fg=WARN_FG,
                 highlightbackground=WARN_BORDER, highlightthickness=1, anchor='w',
                 justify='left', padx=8, pady=4).pack(side='bottom', fill='x', pady=(6, 0))
        # полоса «пресет сменён — пересобрать?» (если протокол правили руками)
        self.switch_bar = tk.Frame(self.out_panel, bg=WARN_BG, highlightthickness=1,
                                   highlightbackground=WARN_BORDER, padx=8, pady=4)
        tk.Label(self.switch_bar, text='Пресет сменён. Пересобрать протокол?', bg=WARN_BG,
                 fg=WARN_FG).pack(side='left')
        ttk.Button(self.switch_bar, text='Оставить как есть',
                   command=lambda: self.switch_bar.pack_forget()).pack(side='right')
        ttk.Button(self.switch_bar, text='Пересобрать',
                   command=self._rebuild_after_switch).pack(side='right', padx=(0, 6))
        f, self.out_txt = self._text(self.out_panel, 6)
        f.pack(fill='both', expand=True)
        self.out_frame = f
        # вид протокола: разделы жирные с отступом; «проверьте» — полоса на полях
        bold = tkfont.Font(font=self.f_text)
        bold.configure(weight='bold')
        self.out_txt.tag_configure('section', font=bold, spacing1=8)
        self.out_txt.tag_configure('first', spacing1=0)
        self.out_txt.tag_configure('check', lmargin1=10, lmargin2=10, lmargincolor=WARN_TEXT)
        self.out_txt.bind('<KeyRelease>', self._unmark_edited, add='+')
        self.out_txt.tag_configure('added', background='#e3eef7')

        # Строка статуса
        st = ttk.Frame(r, padding=(12, 4, 12, 8))
        st.pack(fill='x', side='bottom')
        self.body.pack(fill='both', expand=True)   # после статуса: сжимается тело, а не статус
        line = ttk.Frame(st)
        line.pack(anchor='w', fill='x')
        self.status_lbl = ttk.Label(line, text='')
        self.status_lbl.pack(side='left')
        # первый запуск новой версии: ссылка в пустой строке статуса вместо всплывающего
        # окна; уходит при первом действии, вернётся при запуске, пока её не откроют
        link = tkfont.Font(font=self.f_small)
        link.configure(underline=True)
        self.news_lbl = ttk.Label(line, text=f'Обновлено до {VERSION_LABEL} — что нового?',
                                  foreground=ACCENT, font=link, cursor='hand2')
        self.news_lbl.bind('<Button-1>', lambda e: self.about())
        # появляется после копирования исправленного протокола
        self.mark_prompt = ttk.Button(line, text='Отметить, что пошло не так',
                                      style='Accent.TButton', command=self.mark_case)
        # появляется после смены пресета: вернуть прежний
        self.undo_btn = ttk.Button(line, text='Вернуть', command=self._undo_switch)
        self._undo_to: int | None = None
        # «Отменить» запоминание слова
        self.unlearn_btn = ttk.Button(line, text='Отменить', command=self._unlearn)
        self._learned: str | None = None
        # вопрос «Каким словом это было в записи?» — не блокирует
        self.learn_bar = ttk.Frame(st)
        self._learn_code: str | None = None
        self._learn_cands: list[str] = []
        self.warn_lbl = ttk.Label(st, text='', foreground=WARN_TEXT, justify='left')
        self.warn_lbl.pack(anchor='w')
        self.def_lbl = ttk.Label(st, text='', foreground=MUTED, justify='left')
        self.def_lbl.pack(anchor='w')
        st.bind('<Configure>', lambda e: [w.configure(wraplength=max(200, e.width - 30))
                                          for w in (self.warn_lbl, self.def_lbl, self.status_lbl)])

        r.bind('<Configure>', self._on_resize)
        self._relayout('wide')

    def _relayout(self, mode: str):
        if mode == self.mode:
            return
        self.mode = mode
        if hasattr(self, 'warn_lbl'):
            self._show_marks()
        for p in (self.in_panel, self.out_panel):
            p.grid_forget()
        self.bar_left.pack_forget()
        self.bar_right.pack_forget()
        for w in self.bar_widgets:
            w.grid_forget()
        for i, b in enumerate(self.out_btns):
            b.grid_forget()
            if mode == 'wide':
                b.grid(row=0, column=i, padx=(0, 8))
            else:   # узко: «Сохранить как эталон» — второй строкой
                b.grid(row=i // 2, column=i % 2, padx=(0, 8), pady=2, sticky='w')
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
            self._show_preset_name()
            self.file_lbl.configure(wraplength=0 if self.mode == 'wide' else max(150, e.width - 220))

    # ---------- клавиши ----------
    def _bind_keys(self):
        for w in (self.raw_txt, self.out_txt, self.add_entry):
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
            self.import_xlsx()
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

    def _show_protocol(self, rows):
        """Текст протокола с тегами; прежние теги снимаются полностью."""
        t = self.out_txt
        t.delete('1.0', 'end')
        for tag in ('section', 'first', 'check'):
            t.tag_remove(tag, '1.0', 'end')
        for i, row in enumerate(rows):
            tags = []
            if row.section:
                tags.append('section')
                if i == 0:
                    tags.append('first')
            if row.check:
                tags.append('check')
            t.insert('end', row.text + ('\n' if i < len(rows) - 1 else ''), tuple(tags))
        t.edit_reset()
        t.edit_modified(False)

    def _unmark_edited(self, e):
        """Врач поправил помеченную строку — пометка снимается."""
        if e.keysym in ('Up', 'Down', 'Left', 'Right', 'Home', 'End', 'Prior', 'Next',
                        'Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R'):
            return
        t = self.out_txt
        if 'check' in t.tag_names('insert linestart'):
            t.tag_remove('check', 'insert linestart', 'insert lineend+1c')

    @staticmethod
    def _marks_text(rows, warnings, limit: int = 8) -> str:
        """Причины пометок — «! строка… — причина»; прочие предупреждения — «⚠ …».
        Не больше limit строк: в узком окне список иначе съедает протокол."""
        marks, used = [], set()
        for row in rows:
            for reason in row.check:
                short = row.text if len(row.text) <= 40 else row.text[:40] + '…'
                marks.append(f'! {short} — {reason}')
                used.add(reason)
        # предупреждения без строки в протоколе (пункт не попал) — первыми и всегда
        warns = [f'⚠ {w}' for w in warnings if w not in used]
        room = max(1, limit - len(warns))
        if len(marks) > room:
            rest = len(marks) - (room - 1)
            marks = marks[:room - 1] + [f'… и ещё {rest} — строки с оранжевой полосой в протоколе']
        return '\n'.join(warns + marks)

    def _show_marks(self):
        rows, warnings = getattr(self, '_last_marks', ([], []))
        self.warn_lbl.configure(text=self._marks_text(
            rows, warnings, limit=3 if self.mode == 'narrow' else 8))

    def _status(self, text: str, warnings=(), defaults_line: str = '', ask_mark=False,
                undo=False, rows=()):
        self.status_lbl.configure(text=text, foreground='')
        self.news_lbl.pack_forget()
        self.unlearn_btn.pack_forget()
        if undo:
            self.undo_btn.pack(side='left', padx=(12, 0))
        else:
            self.undo_btn.pack_forget()
        if ask_mark:
            self.mark_prompt.pack(side='left', padx=(12, 0))
        else:
            self.mark_prompt.pack_forget()
        self._last_marks = (list(rows), list(warnings))
        self._show_marks()
        self.def_lbl.configure(text=defaults_line)

    def _show_file_status(self):
        s = self.ctl.file_status
        self.file_lbl.configure(text=s,
                                foreground='#1f7a3f' if s.startswith('✓') else
                                WARN_TEXT if s.startswith(('⚠', '✗', 'Пресетов нет')) else MUTED)
        if self.ctl.details:
            self.details_btn.state(['!disabled'])
        else:
            self.details_btn.state(['disabled'])
        self._refresh_presets()

    # ---------- пресеты ----------
    def _refresh_presets(self):
        m = self.preset_menu
        m.delete(0, 'end')
        for p in self.ctl.presets.list():
            m.add_radiobutton(label=p.name, value=p.id, variable=self.preset_var,
                              command=lambda pid=p.id: self.switch_to(pid))
        if self.ctl.presets.list():
            m.add_separator()
        m.add_command(label='Импорт xlsx…', command=self.import_xlsx, accelerator='Ctrl+O')
        m.add_command(label='Экспорт xlsx…', command=self.export_xlsx,
                      state='normal' if self.ctl.workbook else 'disabled')
        wb = self.ctl.workbook
        self.preset_var.set(self.ctl.preset_id if self.ctl.preset_id is not None else -1)
        self.preset_btn.configure(text=f'Пресет: {wb.name}' if wb else 'Пресет')
        self._show_preset_name()

    def _show_preset_name(self):
        wb = self.ctl.workbook
        name = wb.name if wb else 'пресет не выбран'
        if self.mode == 'narrow' and len(name) > 24:
            name = name[:23] + '…'
        self.head_preset.configure(text=name)

    def _choice(self, title: str, text: str, buttons: list[tuple[str, str]]) -> str | None:
        """Маленькое окно с кнопками; возвращает ключ нажатой или None (закрыли)."""
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        win.resizable(False, False)
        body = ttk.Frame(win, padding=16)
        body.pack(fill='both', expand=True)
        ttk.Label(body, text=text, wraplength=420, justify='left').pack(anchor='w', pady=(0, 12))
        row = ttk.Frame(body)
        row.pack(anchor='e')
        result: list[str | None] = [None]

        def pick(key):
            result[0] = key
            win.destroy()
        for i, (key, label) in enumerate(buttons):
            ttk.Button(row, text=label, style='Accent.TButton' if i == 0 else 'TButton',
                       command=lambda k=key: pick(k)).pack(side='left', padx=(0 if i == 0 else 6, 0))
        win.bind('<Escape>', lambda e: win.destroy())
        win.grab_set()
        win.wait_window()
        return result[0]

    def import_xlsx(self):
        p = filedialog.askopenfilename(title='Импорт пресета из xlsx',
                                       filetypes=[('Excel', '*.xlsx'), ('Все файлы', '*.*')])
        if not p:
            return
        update_id = None
        wb = self.ctl.workbook
        if wb is not None:
            ans = self._choice('Импорт xlsx', f'Файл: {Path(p).name}\n\nСоздать из него новый '
                               f'пресет или обновить текущий «{wb.name}»?',
                               [('new', 'Новый пресет'), ('update', f'Обновить «{wb.name}»'),
                                ('cancel', 'Отмена')])
            if ans in (None, 'cancel'):
                return
            if ans == 'update':
                update_id = self.ctl.preset_id
                if self.ctl.needs_export_before_update(update_id):
                    ans = self._choice(
                        'Импорт xlsx', f'В пресете «{wb.name}» есть эталоны, которых нет в '
                        f'выгруженном файле. При обновлении они пропадут.\n\nСначала выгрузить?',
                        [('export', 'Выгрузить…'), ('go', 'Обновить без выгрузки'),
                         ('cancel', 'Отмена')])
                    if ans in (None, 'cancel'):
                        return
                    if ans == 'export' and not self.export_xlsx():
                        return
        self.ctl.import_xlsx(Path(p), update_id=update_id)
        self._show_file_status()
        if self.ctl.details and not self.ctl.file_status.startswith('✓'):
            self.show_details()

    def export_xlsx(self) -> bool:
        wb = self.ctl.workbook
        if wb is None:
            return False
        from datetime import date
        p = filedialog.asksaveasfilename(title='Экспорт пресета в xlsx', defaultextension='.xlsx',
                                         initialfile=f'{wb.name}-{date.today():%Y-%m-%d}.xlsx',
                                         filetypes=[('Excel', '*.xlsx')])
        if not p:
            return False
        msg = self.ctl.export_xlsx(Path(p))
        self._status(msg)
        self._refresh_presets()
        return msg.startswith('Выгружено')

    def switch_to(self, pid: int):
        if pid == self.ctl.preset_id:
            return
        out = self.out_txt.get('1.0', 'end-1c')
        edited = self.ctl.needs_confirm_regenerate(out)
        prev = self.ctl.preset_id
        self.ctl.switch_preset(pid)
        self._show_file_status()
        self.switch_bar.pack_forget()
        raw = self.raw_txt.get('1.0', 'end-1c').strip()
        if not raw or not out.strip():
            self._status(f'Пресет: {self.ctl.workbook.name}')
            return
        if edited:
            self.switch_bar.pack(fill='x', pady=(0, 6), before=self.out_frame)
            self._status(f'Пресет: {self.ctl.workbook.name}')
            return
        self._undo_to = prev
        self._regenerate_silently(
            raw, f'Пресет: {self.ctl.workbook.name} — протокол пересобран; '
                 f'в буфере прежний — нажмите «Копировать»', undo=True)

    def _regenerate_silently(self, raw: str, status: str, undo=False):
        """Пересобрать без копирования — буфер при смене пресета не меняется."""
        r = self.ctl.generate(raw, copy=False)
        if r.text:
            self._show_protocol(r.rows)
            self._status(status, r.warnings, r.defaults_line, undo=undo, rows=r.rows)
        else:
            self._status(r.status)

    def _rebuild_after_switch(self):
        self.switch_bar.pack_forget()
        raw = self.raw_txt.get('1.0', 'end-1c').strip()
        if raw:
            self._regenerate_silently(
                raw, 'Протокол пересобран; в буфере прежний — нажмите «Копировать»')

    def _undo_switch(self):
        pid, self._undo_to = self._undo_to, None
        if pid is None or not self.ctl.presets.exists(pid):
            return
        self.ctl.switch_preset(pid)
        self._show_file_status()
        raw = self.raw_txt.get('1.0', 'end-1c').strip()
        if raw:
            self._regenerate_silently(
                raw, f'Пресет возвращён: {self.ctl.workbook.name}; '
                     f'в буфере прежний — нажмите «Копировать»')

    def generate(self):
        current = self.out_txt.get('1.0', 'end-1c')
        if self.ctl.needs_confirm_regenerate(current) and not messagebox.askyesno(
                TITLE, 'Заменить исправленный протокол новым?', icon='warning'):
            return
        r = self.ctl.generate(self.raw_txt.get('1.0', 'end-1c'))
        if r.copied:
            self._show_protocol(r.rows)
        self._status(r.status, r.warnings, r.defaults_line, rows=r.rows)
        self._hide_learning()
        self._close_add()
        self._show_unknown([])
        if r.copied:      # подчёркивание — после показа протокола, Ctrl+Enter не ждёт
            self.root.after_idle(lambda: self._show_unknown(self.ctl.find_unknown()))

    # ---------- непонятые слова ----------
    def _show_unknown(self, spans):
        t = self.raw_txt
        for tag in ('unknown', 'learned'):
            t.tag_remove(tag, '1.0', 'end')
        for s, e, _ in spans:
            t.tag_add('unknown', f'1.0+{s}c', f'1.0+{e}c')

    def _unmark_unknown(self, e):
        """Правка слова снимает подчёркивание только с него. Врач печатает в записи —
        режим «Для слова …» отменяется (щелчок мог быть просто чтобы поправить опечатку)."""
        if e.keysym in ('Up', 'Down', 'Left', 'Right', 'Home', 'End', 'Prior', 'Next',
                        'Shift_L', 'Shift_R', 'Control_L', 'Control_R', 'Alt_L', 'Alt_R',
                        'ISO_Next_Group', 'Caps_Lock', 'Escape', 'Tab'):
            return
        if self._add_word is not None:
            self._close_add()
        t = self.raw_txt
        for at in ('insert', 'insert-1c'):
            if 'unknown' in t.tag_names(at):
                t.tag_remove('unknown', f'{at} wordstart', f'{at} wordend')

    def _on_unknown_click(self, e):
        t = self.raw_txt
        at = t.index(f'@{e.x},{e.y}')
        rng = t.tag_prevrange('unknown', f'{at}+1c')
        if rng:
            self._open_add_for_word(t.get(*rng))

    # ---------- «Добавить пункт» ----------
    def _open_add_for_word(self, word: str):
        self._add_word = word
        self.add_for_lbl.configure(text=f'Для слова «{word}» — выберите пункт:')
        self.add_for.pack(fill='x', before=self.add_box.winfo_children()[1])
        self.add_entry.delete(0, 'end')
        # после щелчка Text сам забирает фокус — переводим его, когда щелчок обработан
        self.root.after_idle(self.add_entry.focus_set)
        self._on_add_query()

    def _close_add(self):
        self._add_word = None
        self.add_for.pack_forget()
        self.add_list.pack_forget()
        self.add_entry.delete(0, 'end')
        self._hits = []

    def _on_add_key(self, e):
        if e.keysym not in ('Up', 'Down', 'Return', 'KP_Enter', 'Escape'):
            self._on_add_query()

    def _on_add_query(self):
        q = self.add_entry.get()
        self._hits = self.ctl.search(q) if (q.strip() or self._add_word) else []
        lb = self.add_list
        lb.delete(0, 'end')
        for h in self._hits:
            lb.insert('end', f'{h.label}   —   {h.where}')
        if self._hits:
            lb.configure(height=min(7, len(self._hits)))
            lb.selection_clear(0, 'end')
            lb.selection_set(0)
            lb.pack(fill='x', pady=(2, 0))
        else:
            lb.pack_forget()

    def _move_hit(self, step: int):
        if not self._hits:
            return
        cur = self.add_list.curselection()
        i = max(0, min(len(self._hits) - 1, (cur[0] if cur else -1) + step))
        self.add_list.selection_clear(0, 'end')
        self.add_list.selection_set(i)
        self.add_list.see(i)

    def _add_selected(self, index):
        if index is None:
            cur = self.add_list.curselection()
            index = cur[0] if cur else 0
        if not self._hits or self.ctl.workbook is None:
            return
        hit = self._hits[index]
        word = self._add_word
        old = self.out_txt.get('1.0', 'end-1c')
        res = self.ctl.add_item(old, hit.code, word=word)
        self._apply_added(old, res.text, res.line)
        self._close_add()
        self._show_file_status()
        self._status(res.status)
        if res.learned:
            self._show_learned(word)
        else:
            self._ask_learning(res.code, res.candidates)

    def _apply_added(self, old: str, new: str, line: int):
        """Вставить/заменить строки в поле, не трогая остальной текст и его теги."""
        t = self.out_txt
        old_lines, new_lines = old.splitlines(), new.splitlines()
        diff = len(new_lines) - len(old_lines)
        if diff == 0:
            t.delete(f'{line + 1}.0', f'{line + 1}.end')
            t.insert(f'{line + 1}.0', new_lines[line])
        else:
            start = line - diff + 1
            block = '\n'.join(new_lines[start:line + 1])
            if start < len(old_lines):
                t.insert(f'{start + 1}.0', block + '\n')
            else:
                t.insert('end', ('\n' if old_lines else '') + block)
            heads = {' '.join(s.text.split()) for s in self.ctl.workbook.sections}
            for k in range(start, line + 1):
                if ' '.join(new_lines[k].split()) in heads:
                    t.tag_add('section', f'{k + 1}.0', f'{k + 1}.end')
        for tag in ('check', 'section'):
            if tag == 'check' or ' '.join(new_lines[line].split()) not in {
                    ' '.join(s.text.split()) for s in self.ctl.workbook.sections}:
                t.tag_remove(tag, f'{line + 1}.0', f'{line + 1}.end+1c')
        t.tag_add('added', f'{line + 1}.0', f'{line + 1}.end')
        t.see(f'{line + 1}.0')
        self.root.after(3000, lambda: t.tag_remove('added', '1.0', 'end'))
        self.ctl._last_shown = new

    # ---------- вопрос «каким словом» ----------
    def learn_text(self) -> str:
        if not self.learn_bar.winfo_manager():
            return ''
        return ' '.join(w.cget('text') for w in self.learn_bar.winfo_children()
                        if isinstance(w, (ttk.Label, ttk.Button)))

    def _hide_learning(self):
        for w in self.learn_bar.winfo_children():
            w.destroy()
        self.learn_bar.pack_forget()
        self._learn_code = None

    def _ask_learning(self, code: str, candidates: list[str]):
        self._hide_learning()
        self._learn_code, self._learn_cands = code, candidates
        bar = self.learn_bar
        if candidates:
            ttk.Label(bar, text=f'Это было «{candidates[0]}»?').pack(side='left')
            ttk.Button(bar, text='Да', style='Accent.TButton',
                       command=self._learn_yes).pack(side='left', padx=(8, 0))
            ttk.Button(bar, text='Другое слово…',
                       command=self._show_chips).pack(side='left', padx=(6, 0))
        else:
            ttk.Label(bar, text='Каким словом это было в записи?').pack(side='left')
            self._add_chips(bar)
        ttk.Button(bar, text='Пропустить', command=self._skip_learning).pack(side='left', padx=(6, 0))
        bar.pack(anchor='w', fill='x', pady=(4, 0), after=self.status_lbl.master)

    def _note_words(self) -> list[str]:
        from .text import norm
        from .vocab import SERVICE
        raw = self.raw_txt.get('1.0', 'end-1c')
        out = []
        for w in re.findall(r'[^\s,;:.()«»"!?]+', raw):
            n = norm(w)
            if not re.search(r'[а-яa-z]', n) or re.search(r'\d', n) or n in SERVICE:
                continue          # числа, тире, «на», «и» — учить им бессмысленно и опасно
            if w not in out:
                out.append(w)
        return out

    def _add_chips(self, bar, show_all=False):
        words = self._note_words()
        if self.mode == 'narrow' and not show_all and len(words) > 6:
            words, more = words[-6:], True
        else:
            more = False
        for w in words:
            ttk.Button(bar, text=w, style='Toolbutton',
                       command=lambda w=w: self._learn(w)).pack(side='left', padx=(4, 0))
        if more:
            ttk.Button(bar, text='ещё…', style='Toolbutton',
                       command=lambda: self._rebuild_chips(True)).pack(side='left', padx=(4, 0))
        ttk.Button(bar, text='Запомнить выделенное',
                   command=self._learn_selection).pack(side='left', padx=(8, 0))

    def _rebuild_chips(self, show_all):
        code = self._learn_code
        self._hide_learning()
        self._learn_code = code
        ttk.Label(self.learn_bar, text='Каким словом это было в записи?').pack(side='left')
        self._add_chips(self.learn_bar, show_all)
        ttk.Button(self.learn_bar, text='Пропустить',
                   command=self._skip_learning).pack(side='left', padx=(6, 0))
        self.learn_bar.pack(anchor='w', fill='x', pady=(4, 0), after=self.status_lbl.master)

    def _show_chips(self):
        self._rebuild_chips(False)

    def _learn_yes(self):
        if self._learn_cands:
            self._learn(self._learn_cands[0])

    def _learn_selection(self):
        try:
            word = self.raw_txt.get('sel.first', 'sel.last')
        except tk.TclError:
            self._status('Выделите слово или фразу в записи')
            return
        self._learn(word)

    def _learn(self, word: str):
        code = self._learn_code
        if code is None:
            return
        msg = self.ctl.learn(word, code)
        self._hide_learning()
        self._show_file_status()
        self._status(msg)
        if msg != 'Выберите слово':
            self._show_learned(word)

    def _show_learned(self, word: str):
        """Подсветить выученное слово в записи и дать «Отменить»."""
        t = self.raw_txt
        start = '1.0'
        while True:
            at = t.search(word, start, 'end', nocase=True)
            if not at:
                break
            end = f'{at}+{len(word)}c'
            t.tag_remove('unknown', at, end)
            t.tag_add('learned', at, end)
            start = end
        self._learned = word
        if self.ctl.last_learn_broke:
            self.status_lbl.configure(foreground=WARN_TEXT)
        self.unlearn_btn.pack(side='left', padx=(12, 0))

    def _unlearn(self):
        if self._learned:
            self._status(self.ctl.unlearn(self._learned))
            self._show_file_status()
            self.raw_txt.tag_remove('learned', '1.0', 'end')
            self._learned = None

    def _skip_learning(self):
        if self._learn_code:
            self.ctl.skip_learning(self._learn_code)
        self._hide_learning()

    def copy(self):
        text = self.out_txt.get('1.0', 'end-1c').strip()
        if text:
            status = self.ctl.copy(text)
            if self.ctl.last_copy_edited:
                self._status(f'{status}. Вы исправили протокол —', ask_mark=True)
            else:
                self._status(status)

    def mark_case(self):
        if self.ctl.last_protocol is None:
            self._status('Сначала сформируйте протокол')
            return
        MarkCaseDialog(self, self.raw_txt.get('1.0', 'end-1c').strip(),
                       self.out_txt.get('1.0', 'end-1c').strip())

    def save_reference(self):
        raw = self.raw_txt.get('1.0', 'end-1c').strip()
        text = self.out_txt.get('1.0', 'end-1c').strip()
        wb = self.ctl.workbook
        if not (raw and text and wb):
            self._status('Сначала сформируйте протокол')
            return
        if messagebox.askyesno(TITLE, f'Сохранить запись и протокол как эталон в пресет\n'
                                      f'«{wb.name}»?\n\nЗапись: {raw[:200]}'):
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

    def about(self) -> AboutDialog:
        self.ctl.mark_whats_new_seen()
        self.news_lbl.pack_forget()
        return AboutDialog(self)

    def _toggle_diag(self):
        self.ctl.set_diagnostics(self.diag_var.get())
        self._show_diag()
        if self.ctl.diagnostics:
            self._status(f'Диагностика включена: {self.ctl.diag_dir}')
        else:
            self._status('Диагностика выключена')

    def _show_diag(self):
        on = self.ctl.diagnostics
        self.head_lbl.configure(text='● Диагностика' if on else '', fg=BADGE_BG)
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


def _preset_about(ctl: Controller) -> str:
    wb = ctl.workbook
    if wb is None:
        return 'не выбран'
    info = next((p for p in ctl.presets.list() if p.id == ctl.preset_id), None)
    when = f', импорт {info.imported_at[:10]}' if info and info.imported_at else ''
    return f'{wb.name} (из {wb.source or "—"}{when})'


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
        if not _resource(CHANGELOG).is_file():          # забыт --add-data в сборке
            raise FileNotFoundError(f'нет {CHANGELOG} в сборке')
        return 0
    except Exception as e:
        print(f'selftest-ui: {e}', file=sys.stderr)
        return 1


class AboutDialog:
    """«О программе»: версия, «Что нового» (текущая версия сверху), где лежат данные."""

    def __init__(self, app: App):
        from .changelog import parse, spans
        ctl = app.ctl
        self.top = win = tk.Toplevel(app.root)
        win.title(f'{TITLE} — о программе')
        win.geometry('600x620')
        win.transient(app.root)
        box = ttk.Frame(win, padding=(14, 12, 14, 6))
        box.pack(fill='x')
        ttk.Label(box, text=window_title(), font=app.f_title).pack(anchor='w')
        ttk.Label(box, text=DISCLAIMER, foreground=MUTED, wraplength=560).pack(anchor='w', pady=(4, 0))
        ttk.Label(box, text='Что нового', font=app.f_label).pack(anchor='w', pady=(12, 0))

        f, txt = app._text(win, 16)
        f.pack(fill='both', expand=True, padx=14)
        self.news_txt = txt
        fam = app.f_text.actual('family')
        txt.tag_configure('version', font=(fam, 12, 'bold'), foreground=ACCENT,
                          spacing1=10, spacing3=4)
        txt.tag_configure('bold', font=(fam, 11, 'bold'))
        txt.tag_configure('bullet', lmargin1=6, lmargin2=24, spacing1=2)
        path = _resource(CHANGELOG)
        try:
            releases = parse(path.read_text(encoding='utf-8'))
        except OSError:
            releases = []
        if not releases:
            txt.insert('end', f'Журнал изменений не найден: {path}')
        for k, rel in enumerate(releases):
            txt.insert('end', ('' if k == 0 else '\n') + rel.title + '\n', 'version')
            for line in rel.lines:
                tags: tuple[str, ...] = ()
                if line.startswith('- '):
                    line, tags = '•  ' + line[2:], ('bullet',)
                for part, bold in spans(line):
                    txt.insert('end', part, tags + (('bold',) if bold else ()))
                txt.insert('end', '\n', tags)
        txt.configure(state='disabled')

        diag = 'включена' if ctl.diagnostics else 'выключена'
        info = (f'Пресет: {_preset_about(ctl)}\n'
                f'Журнал: {ctl.journal.db_path}\n'
                f'Диагностика ({diag}): {ctl.diag_dir}')
        foot = ttk.Frame(win, padding=(14, 8, 14, 12))
        foot.pack(fill='x')
        ttk.Label(foot, text=info, foreground=MUTED, font=app.f_small,
                  wraplength=440, justify='left').pack(side='left', anchor='w')
        ttk.Button(foot, text='Закрыть', command=win.destroy).pack(side='right', anchor='s')
        win.bind('<Escape>', lambda e: win.destroy())


class MarkCaseDialog:
    """«Отметить ошибку»: один понятный выбор, остальное программа сохранит сама."""
    CHOICES = [
        ('me', 'записал(а) неточно: опечатка, сокращение, забыл(а) что-то написать'),
        ('program', 'я записал(а) правильно, а программа поняла не так'),
        ('classifier', 'в списке нет нужного пункта — пришлось писать свой текст'),
        ('unknown', 'просто сохраните — разберутся'),
    ]

    def __init__(self, app: App, raw: str, corrected: str):
        self.app, self.corrected = app, corrected
        self.win = win = tk.Toplevel(app.root)
        win.title('Отметить ошибку')
        win.transient(app.root)
        win.resizable(True, False)
        body = ttk.Frame(win, padding=16)
        body.pack(fill='both', expand=True)

        ttk.Label(body, text='Что пошло не так?', font=app.f_title).pack(anchor='w', pady=(0, 8))
        last = app.ctl.last_protocol
        self.unchanged = last is not None and corrected.strip() == last.text.strip()
        if self.unchanged:
            ttk.Label(body, foreground=WARN_TEXT, wraplength=420, padding=(0, 0, 0, 8),
                      text='Протокол не исправлен — разработчик не увидит, что не так. '
                           'Исправьте протокол в окне или напишите внизу пару слов.'
                      ).pack(anchor='w')
        self.kind = tk.StringVar(value='unknown')
        for key, hint in self.CHOICES:
            ttk.Radiobutton(body, text=CASE_KINDS[key], value=key, variable=self.kind,
                            command=self._toggle_raw).pack(anchor='w')
            ttk.Label(body, text=hint, foreground=MUTED, wraplength=420,
                      padding=(28, 0, 0, 6)).pack(anchor='w')

        self.raw_box = ttk.Frame(body)
        ttk.Label(self.raw_box, text='Как надо было записать:').pack(anchor='w', pady=(6, 2))
        self.raw_entry = ttk.Entry(self.raw_box, font=app.f_text)
        self.raw_entry.insert(0, raw)
        self.raw_entry.pack(fill='x')

        self.after_raw = ttk.Label(body, text=(
            'Что не так? Своими словами:' if self.unchanged
            else 'Своими словами, если хотите (необязательно):'))
        self.after_raw.pack(anchor='w', pady=(10, 2))
        self.comment = ttk.Entry(body, font=app.f_text)
        self.comment.pack(fill='x')

        btns = ttk.Frame(body)
        btns.pack(fill='x', pady=(14, 0))
        ttk.Button(btns, text='Сохранить', style='Accent.TButton',
                   command=self.save).pack(side='right')
        ttk.Button(btns, text='Отмена', command=win.destroy).pack(side='right', padx=8)
        win.bind('<Escape>', lambda e: win.destroy())
        win.minsize(460, 0)
        win.grab_set()
        self.comment.focus_set()

    def _toggle_raw(self):
        if self.kind.get() == 'me':
            self.raw_box.pack(fill='x', before=self.after_raw)
            self.raw_entry.focus_set()
        else:
            self.raw_box.pack_forget()

    def save(self):
        kind = self.kind.get()
        status = self.app.ctl.mark_case(
            kind, self.corrected,
            corrected_raw=self.raw_entry.get().strip() if kind == 'me' else None,
            comment=self.comment.get())
        self.win.destroy()
        self.app._status(status)
