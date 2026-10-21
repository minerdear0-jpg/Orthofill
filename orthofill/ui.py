"""Окно Orthofill: tkinter + тема sv-ttk (в стиле Windows 11)."""
from __future__ import annotations

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
        f.pack(fill='both', expand=True)

        self.out_panel = ttk.Frame(self.body)
        ttk.Label(self.out_panel, text='ПРОТОКОЛ (МОЖНО ПРАВИТЬ)', font=self.f_label,
                  foreground=MUTED).pack(anchor='w', pady=(0, 3))
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

        # Строка статуса
        st = ttk.Frame(r, padding=(12, 4, 12, 8))
        st.pack(fill='x', side='bottom')
        self.body.pack(fill='both', expand=True)   # после статуса: сжимается тело, а не статус
        line = ttk.Frame(st)
        line.pack(anchor='w', fill='x')
        self.status_lbl = ttk.Label(line, text='')
        self.status_lbl.pack(side='left')
        # появляется после копирования исправленного протокола
        self.mark_prompt = ttk.Button(line, text='Отметить, что пошло не так',
                                      style='Accent.TButton', command=self.mark_case)
        # появляется после смены пресета: вернуть прежний
        self.undo_btn = ttk.Button(line, text='Вернуть', command=self._undo_switch)
        self._undo_to: int | None = None
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
        out, used = [], set()
        for row in rows:
            for reason in row.check:
                short = row.text if len(row.text) <= 40 else row.text[:40] + '…'
                out.append(f'! {short} — {reason}')
                used.add(reason)
        out += [f'⚠ {w}' for w in warnings if w not in used]
        if len(out) > limit:
            rest = len(out) - (limit - 1)
            out = out[:limit - 1] + [f'… и ещё {rest} — строки с оранжевой полосой в протоколе']
        return '\n'.join(out)

    def _show_marks(self):
        rows, warnings = getattr(self, '_last_marks', ([], []))
        self.warn_lbl.configure(text=self._marks_text(
            rows, warnings, limit=3 if self.mode == 'narrow' else 8))

    def _status(self, text: str, warnings=(), defaults_line: str = '', ask_mark=False,
                undo=False, rows=()):
        self.status_lbl.configure(text=text)
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

    def about(self):
        wb = self.ctl.workbook
        messagebox.showinfo(TITLE, f'{window_title()}\n\n{DISCLAIMER}\n\n'
                                   f'Пресет:\n{_preset_about(self.ctl)}\n\n'
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
        return 0
    except Exception as e:
        print(f'selftest-ui: {e}', file=sys.stderr)
        return 1


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
