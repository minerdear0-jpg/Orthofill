"""Поле записи в режиме оболочки (0.5): строка — путь по дереву пресета.

Набор → серым, до чего Tab развернёт строку; неоднозначно — список (как
`?` в Cisco IOS); слово без кандидатов — красным сразу. Tab — развернуть,
`?` — ветки уровня, ↑/↓ — выбор в списке, Enter — строка готова (на группе —
ветки), Esc — закрыть список, Backspace сразу после разворота — вернуть
набранное. Привязки — с add='+' после HintBox: тот в режиме оболочки молчит."""
from __future__ import annotations

import re
import tkinter as tk

from .shell import SEP, Path, children_of, format_path, is_leaf, parse_line, resolve, split_line

_SEL_BG, _BORDER = '#e3eef7', '#1f5f8b'


class ShellBox:
    def __init__(self, app, text: tk.Text):
        self.app, self.text = app, text
        self.choices: list[Path] = []
        self.selected = -1
        self.ghost = ''
        self.list_shown = False
        self._expanded: tuple[str, str] | None = None     # (строка до, строка после) последнего разворота
        text.tag_configure('shell_bad', foreground='#b42318', underline=True)
        text.tag_configure('shell_ok', foreground='#1b1b1a')
        bg = text.cget('background')
        self.tail = tk.Label(text, text='', fg='#8a95a1', bg=bg, font=app.f_small, bd=0, padx=4)
        self.frame = tk.Frame(app.root, bg='#ffffff', highlightthickness=1,
                              highlightbackground='#c9ced4')
        for seq, fn in (('<Tab>', self._tab), ('<Return>', self._enter), ('<KP_Enter>', self._enter),
                        ('<Escape>', self._escape), ('<Up>', lambda e: self._move(-1)),
                        ('<Down>', lambda e: self._move(1)), ('<KeyPress>', self._keypress),
                        ('<KeyRelease>', self._keyrelease)):
            text.bind(seq, fn, add='+')
        text.bind('<FocusOut>', lambda e: self.close(), add='+')

    # ---------- состояние ----------
    def on(self) -> bool:
        return bool(self.app.ctl.shell_mode and self.app.ctl.workbook is not None)

    @property
    def wb(self):
        return self.app.ctl.workbook

    def _line(self) -> tuple[int, str]:
        n = int(self.text.index('insert').split('.')[0])
        return n, self.text.get(f'{n}.0', f'{n}.end')

    def _state(self):
        """(номер строки, строка, выбранные уровни, набранное, начало набранного)."""
        n, line = self._line()
        done, typed = split_line(self.wb, line)
        sep = SEP.strip()
        start = line.rindex(sep) + 1 if sep in line else 0
        while start < len(line) and line[start] == ' ':
            start += 1
        return n, line, done, typed, start

    def close(self):
        self.choices, self.selected, self.list_shown = [], -1, False
        self.ghost = ''
        self.tail.place_forget()
        self.frame.place_forget()

    # ---------- после набора ----------
    def update(self):
        t = self.text
        t.tag_remove('shell_bad', '1.0', 'end')
        self._mark_ok()
        if not self.on():
            self.close()
            return
        n, line, done, typed, start = self._state()
        self.close()
        if done is None or not typed.strip():
            return
        r = resolve(self.wb, done, typed, self.app.ctl.shell_synonyms())
        if not r.leaves:
            words = list(re.finditer(r'\S+', line[start:]))
            k = min(r.bad_word or 0, len(words) - 1)
            if words:
                w = words[k]
                t.tag_add('shell_bad', f'{n}.{start + w.start()}', f'{n}.{start + w.end()}')
            return
        unique = len(r.leaves) == 1
        if r.common != done and (unique or len(r.common) > len(done)):
            self.ghost = format_path(self.wb, r.common if not unique else r.leaves[0])
            self._show_ghost()
        if not unique and len(r.choices) > 1:
            self._show_list(r.choices)

    def _mark_ok(self):
        """Готовые строки (путь до конца) — отмечены."""
        t = self.text
        t.tag_remove('shell_ok', '1.0', 'end')
        if not self.on():
            return
        last = int(t.index('end-1c').split('.')[0])
        for n in range(1, last + 1):
            line = t.get(f'{n}.0', f'{n}.end')
            path = parse_line(self.wb, line) if SEP.strip() in line else None
            if path and is_leaf(self.wb, path):
                t.tag_add('shell_ok', f'{n}.0', f'{n}.end')

    # ---------- показ ----------
    def _show_ghost(self):
        box = self.text.bbox('insert')
        if box is None:
            return
        self.tail.configure(text=f'→ {self.ghost}')
        self.tail.place(x=box[0] + 4, y=box[1], bordermode='outside')

    def _show_list(self, choices: list[Path], selected: int = -1):
        self.choices, self.selected = choices, selected
        f, t, app = self.frame, self.text, self.app
        for w in f.winfo_children():
            w.destroy()
        for i, path in enumerate(choices[:40]):
            sel = i == selected
            row = tk.Frame(f, bg=_SEL_BG if sel else '#ffffff', highlightthickness=1,
                           highlightbackground=_BORDER if sel else '#ffffff')
            row.pack(fill='x', padx=2, pady=(2 if i == 0 else 0, 0))
            bg = row.cget('bg')
            node = self.wb.by_id[path[-1]]
            tk.Label(row, text=' '.join(node.text.split())[:90], font=app.f_text, bg=bg,
                     anchor='w').pack(side='left', padx=(6, 0))
            where = ' › '.join(' '.join(self.wb.by_id[c].text.split())[:24] for c in path[:-1])
            tk.Label(row, text=f'{where}  {path[-1]}'.strip(), font=app.f_small, fg='#8a95a1',
                     bg=bg).pack(side='right', padx=(8, 6))
            for w in (row, *row.winfo_children()):
                w.bind('<Button-1>', lambda e, k=i: self._accept(self.choices[k]))
        tk.Label(f, text='↑↓ — выбрать · Tab/Enter — принять · Esc — закрыть', font=app.f_small,
                 fg='#8a95a1', bg='#ffffff', anchor='w').pack(fill='x', padx=8, pady=(2, 3))
        box = t.bbox('insert') or (0, 0, 0, 16)
        f.update_idletasks()
        rx = t.winfo_rootx() - app.root.winfo_rootx()
        ry = t.winfo_rooty() - app.root.winfo_rooty()
        width = min(t.winfo_width(), 640)
        top = ry + box[1] + box[3] + 2
        if top + f.winfo_reqheight() > app.root.winfo_height():
            top = max(0, ry + box[1] - f.winfo_reqheight() - 2)
        f.place(x=rx + min(box[0], max(0, t.winfo_width() - width)), y=top, width=width)
        f.lift()
        self.list_shown = True

    # ---------- правка строки ----------
    def _set_line(self, n: int, new: str):
        """Строка n целиком → new; одна отмена возвращает прежнюю."""
        t = self.text
        old = t.get(f'{n}.0', f'{n}.end')
        t.configure(autoseparators=False)
        t.edit_separator()
        t.delete(f'{n}.0', f'{n}.end')
        t.insert(f'{n}.0', new)
        t.edit_separator()
        t.configure(autoseparators=True)
        t.mark_set('insert', f'{n}.end')
        self._expanded = (old, new)

    def _path_text(self, path: Path) -> str:
        return format_path(self.wb, path) + ('' if is_leaf(self.wb, path) else SEP)

    def _accept(self, path: Path) -> bool:
        n, _ = self._line()
        self._set_line(n, self._path_text(path))
        self.close()
        self.text.focus_set()
        self.update()
        return True

    def _finish(self) -> bool:
        """Строка — готовый путь: отметить, перейти на новую строку."""
        t = self.text
        n, line = self._line()
        path = parse_line(self.wb, line)
        if not path or not is_leaf(self.wb, path):
            return False
        t.mark_set('insert', f'{n}.end')
        t.insert('insert', '\n')
        self.close()
        self._expanded = None
        self._mark_ok()
        return True

    def _branches(self) -> bool:
        """Список веток: набранного нет — ветки последнего уровня; есть — варианты."""
        n, line, done, typed, _ = self._state()
        if done is None:
            return False
        if typed.strip():
            r = resolve(self.wb, done, typed, self.app.ctl.shell_synonyms())
            ch = r.choices if len(r.leaves) != 1 else [r.leaves[0]]
        else:
            if done and is_leaf(self.wb, done):
                return False
            ch = [done + (c.id,) for c in children_of(self.wb, done[-1] if done else None)]
        if ch:
            self._show_list(ch, 0 if typed.strip() == '' else -1)
        return bool(ch)

    # ---------- клавиши ----------
    def _tab(self, e):
        if not self.on() or (e is not None and e.state & (0x1 | 0x4)):
            return None
        if self.list_shown and self.selected >= 0:
            return 'break' if self._accept(self.choices[self.selected]) else None
        n, line, done, typed, _ = self._state()
        if done is None:
            return 'break'
        if typed.strip():
            r = resolve(self.wb, done, typed, self.app.ctl.shell_synonyms())
            if len(r.leaves) == 1:
                self._accept(r.leaves[0])
            elif r.leaves and len(r.common) > len(done):
                self._accept(r.common)
            elif r.leaves:
                self._show_list(r.choices)
            return 'break'
        self._branches()
        return 'break'

    def _enter(self, e):
        if not self.on():
            return None
        if self.list_shown and self.selected >= 0:
            self._accept(self.choices[self.selected])
            self._finish()
            return 'break'
        n, line, done, typed, _ = self._state()
        if not line.strip():
            return None                     # пустая строка — обычный перенос
        if self._finish():
            return 'break'
        if done is not None and typed.strip():
            r = resolve(self.wb, done, typed, self.app.ctl.shell_synonyms())
            if len(r.leaves) == 1:
                self._accept(r.leaves[0])
                self._finish()
                return 'break'
        self._branches()
        return 'break'

    def _escape(self, e):
        if self.on() and self.list_shown:
            self.close()
            return 'break'
        return None

    def _move(self, step: int):
        if not (self.on() and self.list_shown and self.choices):
            return None
        self.selected = max(0, min(len(self.choices) - 1, self.selected + step))
        self._show_list(self.choices, self.selected)
        return 'break'

    def _keypress(self, e):
        if not self.on():
            return None
        if e.char == '?':                   # ветки уровня; в текст не вставляется
            self._branches()
            return 'break'
        if e.keysym == 'BackSpace':         # не отдельной привязкой: общая <KeyPress>
            return self._backspace(e)       # (счётчик набора 0.4) иначе не увидит Backspace
        return None

    def _keyrelease(self, e):
        if not self.on() or e.keysym in ('Up', 'Down', 'Tab', 'Return', 'KP_Enter', 'Escape',
                                         'question', 'Shift_L', 'Shift_R', 'Control_L',
                                         'Control_R', 'Left', 'Right'):
            return None
        if e.keysym != 'BackSpace':
            self._expanded = None
        self.update()
        return None

    def _backspace(self, e):
        """Сразу после разворота — вернуть набранное (как отмена дополнения)."""
        if not self.on() or self._expanded is None:
            return None
        n, line = self._line()
        old, new = self._expanded
        if line != new:
            self._expanded = None
            return None
        self._set_line(n, old)
        self._expanded = None
        self.update()
        return 'break'
