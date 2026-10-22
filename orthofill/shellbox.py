"""Поле записи в режиме оболочки (0.5): строка — путь по дереву пресета.

Набор → серым, до чего Tab развернёт строку; неоднозначно — список (как
`?` в Cisco IOS); слово без кандидатов — красным сразу. Tab — развернуть,
`?` — ветки уровня, ↑/↓ — выбор в списке, Enter — строка готова (на группе —
ветки), Esc — закрыть список, Backspace сразу после разворота — вернуть
набранное. Привязки — с add='+' после HintBox: тот в режиме оболочки молчит."""
from __future__ import annotations

import re
import tkinter as tk

from .predict import predict, rank
from .shell import SEP, Path, children_of, format_path, is_leaf, parse_line, resolve, split_line

_SEL_BG, _BORDER = '#e3eef7', '#1f5f8b'


class ShellBox:
    dwell_ms = 400          # мс: курсор, пришедший стрелкой, «намеренно» стоит на уровне

    def __init__(self, app, text: tk.Text):
        self.app, self.text = app, text
        self.choices: list[Path] = []
        self.selected = -1
        self.ghost = ''
        self.list_shown = False
        self._expanded: tuple[str, str] | None = None     # (строка до, строка после) последнего разворота
        self._replace: tuple[int, int] | None = None       # (строка, уровень): список — соседи уровня
        self._list_line: str | None = None   # список открыт явно (?/Tab) на этой строке
        self.prediction = None               # 0.5 b2: кандидат следующей строки (пустая строка)
        self._preds: list = []
        self._pred_taken = False             # принят (Tab/Ctrl+→) — не считать «проигнорирован»
        self._stars: set = set()             # обычные у врача пункты в списке — «★»
        self._seen: tuple[int, str] | None = None   # строка, по которой последний раз пересчитали
        self._pred_line = 0                  # строка, для которой предсказание
        self._ignored_at: tuple | None = None   # (строка, путь): «проигнорирован» уже записан
        self._stats_job = None
        self._dwell_job = None
        # телеметрия текущей строки (без текста): Tab, ?, набрано символов, «не подходит» показано
        self._stat = {'tabs': 0, 'questions': 0, 'typed': 0, 'bad': False}
        text.tag_configure('shell_bad', foreground='#b42318', underline=True)
        text.tag_configure('shell_ok', foreground='#1b1b1a')
        bg = text.cget('background')
        self.tail = tk.Label(text, text='', fg='#8a95a1', bg=bg, font=app.f_small, bd=0, padx=4)
        self.frame = tk.Frame(app.root, bg='#ffffff', highlightthickness=1,
                              highlightbackground='#c9ced4')
        for seq, fn in (('<Tab>', self._tab), ('<Return>', self._enter), ('<KP_Enter>', self._enter),
                        ('<Escape>', self._escape), ('<Up>', lambda e: self._move(-1)),
                        ('<Down>', lambda e: self._move(1)), ('<KeyPress>', self._keypress),
                        ('<KeyRelease>', self._keyrelease),
                        ('<Control-Right>', self._ctrl_right),
                        ('<Shift-Tab>', lambda e: self._shift_tab()),
                        ('<Left>', lambda e: self._arrow(-1, e)),
                        ('<Right>', lambda e: self._arrow(1, e))):
            text.bind(seq, fn, add='+')
        try:                                        # X11: Shift+Tab приходит как ISO_Left_Tab
            text.bind('<ISO_Left_Tab>', lambda e: self._shift_tab(), add='+')
        except tk.TclError:
            pass
        text.bind('<FocusOut>', lambda e: self.close(), add='+')
        text.bind('<ButtonRelease-1>', lambda e: self.on() and self.update(), add='+')

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
        self._cancel_dwell()
        self._replace = None
        self._list_line = None
        self._stars = set()
        self.choices, self.selected, self.list_shown = [], -1, False
        self.ghost = ''
        self.tail.place_forget()
        self.frame.place_forget()

    def _track(self, action: str, **data):
        try:
            self.app.ctl.track('shell', action=action, **data)
        except Exception:
            pass

    # ---------- после набора ----------
    def update(self):
        t = self.text
        t.tag_remove('shell_bad', '1.0', 'end')
        self._mark_ok()
        if not self.on():
            self.close()
            return
        n, line, done, typed, start = self._state()
        self._seen = (n, line)
        self.close()
        self._schedule_stats()
        if not line.strip():
            self._predict(n)
            return
        if self.prediction is not None and not self._pred_taken and n == self._pred_line \
                and self._ignored_at != (n, self.prediction.path):
            self._track('predict', outcome='ignored', source=self.prediction.source)
            self._ignored_at = (n, self.prediction.path)
        self.prediction = None
        self._pred_taken = False
        if done is None or not typed.strip():
            return
        full = parse_line(self.wb, line)
        if full and is_leaf(self.wb, full):     # строка уже готова — подсказывать нечего
            return
        r = resolve(self.wb, done, typed, self.app.ctl.shell_synonyms())
        if not r.leaves:
            words = list(re.finditer(r'\S+', line[start:]))
            k = min(r.bad_word or 0, len(words) - 1)
            if words:
                w = words[k]
                t.tag_add('shell_bad', f'{n}.{start + w.start()}', f'{n}.{start + w.end()}')
                if not self._stat['bad']:
                    self._stat['bad'] = True
                    self._track('bad_word', word_index=k)
            return
        unique = len(r.leaves) == 1
        if r.common != done and (unique or len(r.common) > len(done)):
            self.ghost = format_path(self.wb, r.common if not unique else r.leaves[0])
            self._show_ghost()
        if not unique and len(r.choices) > 1:
            self._show_list(self._rank(r.choices), 0)     # карусель: первый выбран, Tab — дальше

    # ---------- предсказание (0.5 b2) ----------
    def _rank(self, paths):
        return rank(paths, self.app.ctl.path_stats())

    def _note_paths(self, n: int) -> list[Path]:
        """Готовые строки записи: ниже курсора, затем выше — последний элемент —
        строка прямо над курсором (от неё идёт предсказание), всё — «уже записано»."""
        t = self.text
        last = int(t.index('end-1c').split('.')[0])

        def leaf(k):
            line = t.get(f'{k}.0', f'{k}.end')
            p = parse_line(self.wb, line) if SEP.strip() in line else None
            return p if p and is_leaf(self.wb, p) else None
        below = [p for k in range(n + 1, last + 1) if (p := leaf(k))]
        above = [p for k in range(1, n) if (p := leaf(k))]
        return below + above

    def _schedule_stats(self):
        """Длинная история досчитывается тиками в простое (окно не ждёт)."""
        if self._stats_job is None and self.app.ctl.path_stats_pending():
            self._stats_job = self.app.root.after(50, self._stats_tick)

    def _stats_tick(self):
        self._stats_job = None
        if not self.on():
            return
        self.app.ctl.path_stats()
        if self.app.ctl.path_stats_pending():
            self._stats_job = self.app.root.after(50, self._stats_tick)

    def _predict(self, n: int):
        self._preds = predict(self.wb, self._note_paths(n), self.app.ctl.path_stats())
        self.prediction = self._preds[0] if self._preds else None
        self._pred_line = n
        self._pred_taken = False
        if self.prediction is not None:
            path = self.prediction.path
            self.ghost = format_path(self.wb, path) + ('' if is_leaf(self.wb, path) else ' › …')
            self._show_ghost()

    def _take_prediction(self, levels: int | None) -> bool:
        """Принять предсказание: целиком (levels=None) или до levels уровней."""
        pred = self.prediction
        if pred is None:
            return False
        path = pred.path if levels is None else pred.path[:levels]
        n, _ = self._line()
        self._set_line(n, self._path_text(path))
        if not self._pred_taken:
            self._track('predict', outcome='accepted' if levels is None else 'level',
                        source=pred.source)
        self._pred_taken = True
        self.close()
        if levels is None and not is_leaf(self.wb, path):
            self._branches()
        return True

    def _fresh_prediction(self, n: int, line: str) -> None:
        """Предсказание — для этой строки (курсор могли увести стрелкой или мышью)."""
        if not line.strip() and self._pred_line != n:
            self._predict(n)

    def _ctrl_right(self, e):
        """Ctrl+→ — один следующий уровень предсказанной строки."""
        if not self.on() or (e is not None and e.state & 0x1):
            return None
        n, line = self._line()
        self._fresh_prediction(n, line)
        if self.prediction is None or self._pred_line != n:
            return None
        path = self.prediction.path
        for k in range(len(path)):
            if line == ('' if k == 0 else self._path_text(path[:k])):
                self._take_prediction(k + 1)
                return 'break'
        return None

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

    def _cycle(self, step: int) -> bool:
        """Карусель (как Tab в fish): следующий вариант по кругу — без пересчёта дерева,
        только выделение (зажатый Tab — десятки нажатий в секунду)."""
        if not (self.list_shown and self.choices):
            return False
        n = min(len(self.choices), len(self._rows))
        old = self.selected
        self.selected = (self.selected + step) % n if self.selected >= 0 else (0 if step > 0 else n - 1)
        for i in (old, self.selected):
            if 0 <= i < len(self._rows):
                sel = i == self.selected
                row = self._rows[i]
                bg = _SEL_BG if sel else '#ffffff'
                row.configure(bg=bg, highlightbackground=_BORDER if sel else '#ffffff')
                for w in row.winfo_children():
                    w.configure(bg=bg)
        return True

    def _shift_tab(self):
        if not self.on():
            return None
        self._cycle(-1)
        return 'break'              # в оболочке Shift+Tab не уводит фокус из записи

    def _show_list(self, choices: list[Path], selected: int = -1):
        self.choices, self.selected = choices, selected
        f, t, app = self.frame, self.text, self.app
        for w in f.winfo_children():
            w.destroy()
        self._rows = []
        for i, path in enumerate(choices[:40]):
            sel = i == selected
            star = '★ ' if path in self._stars else ''
            row = tk.Frame(f, bg=_SEL_BG if sel else '#ffffff', highlightthickness=1,
                           highlightbackground=_BORDER if sel else '#ffffff')
            row.pack(fill='x', padx=2, pady=(2 if i == 0 else 0, 0))
            self._rows.append(row)
            bg = row.cget('bg')
            node = self.wb.by_id[path[-1]]
            tk.Label(row, text=star + ' '.join(node.text.split())[:90], font=app.f_text, bg=bg,
                     anchor='w').pack(side='left', padx=(6, 0))
            where = ' › '.join(' '.join(self.wb.by_id[c].text.split())[:24] for c in path[:-1])
            tk.Label(row, text=f'{where}  {path[-1]}'.strip(), font=app.f_small, fg='#8a95a1',
                     bg=bg).pack(side='right', padx=(8, 6))
            for w in (row, *row.winfo_children()):
                w.bind('<Button-1>', lambda e, k=i: self._click(k))
        tk.Label(f, text='Tab — следующий · Shift+Tab — назад · Enter — принять · Esc — закрыть', font=app.f_small,
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

    def _click(self, k: int) -> bool:
        """Щелчок по строке списка — как Enter: в списке соседей — замена уровня."""
        if not (0 <= k < len(self.choices)):
            return False
        if self._replace:
            return self._replace_level(self.choices[k])
        return self._accept(self.choices[k])

    def _accept(self, path: Path, rest: list[str] | None = None) -> bool:
        n, _ = self._line()
        _, _, _, typed, _ = self._state()
        tail = ' '.join(rest or [])
        self._stat['typed'] += max(0, len(typed.strip()) - len(tail))   # набрано — до разворота
        pred = self.prediction
        if pred is not None and not self._pred_taken and self._pred_line == n \
                and any(path == p.path for p in self._preds):
            self._track('predict', outcome='accepted', source=pred.source)
            self._pred_taken = True
        self._set_line(n, self._path_text(path) + tail)
        self.close()
        self.text.focus_set()
        self.update()
        if not tail and not is_leaf(self.wb, path) and not self.list_shown:
            self._branches()            # группа — сразу её ветки (как Tab по предсказанию)
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
        self.app.root.after_idle(self.update)     # новая строка — предсказание
        st = self._stat
        self._track('line_done', depth=len(path), tabs=st['tabs'], questions=st['questions'],
                    typed_chars=st['typed'], line_chars=len(line))
        self._stat = {'tabs': 0, 'questions': 0, 'typed': 0, 'bad': False}
        return True

    def _branches(self) -> bool:
        """Список веток: набранного нет — ветки последнего уровня; есть — варианты."""
        n, line, done, typed, _ = self._state()
        self._fresh_prediction(n, line)
        if not line.strip() and self._preds:     # пустая строка — что дальше по файлу
            self._stars = {p.path for p in self._preds if p.usual}
            self._show_list([p.path for p in self._preds], 0)
            self._list_line = line
            return True
        if done is None:
            return False
        if typed.strip():
            r = resolve(self.wb, done, typed, self.app.ctl.shell_synonyms())
            ch = self._rank(r.choices) if len(r.leaves) != 1 else [r.leaves[0]]
            if ch:
                self._show_list(ch, 0)
                self._list_line = line
            return bool(ch)
        else:
            if done and is_leaf(self.wb, done):
                return False
            ch = self._rank([done + (c.id,) for c in children_of(self.wb, done[-1] if done else None)])
        if ch:
            self._show_list(ch, 0)
            self._list_line = line
        return bool(ch)

    # ---------- клавиши ----------
    def _tab(self, e):
        if not self.on() or (e is not None and e.state & (0x1 | 0x4)):
            return None
        self._stat['tabs'] += 1
        n, line, done, typed, _ = self._state()
        if self.list_shown and self.choices:         # Tab листает, Enter подтверждает
            if self._list_line is None and done is not None and typed.strip():
                # список открылся сам при наборе: первый Tab — дополнить общее начало
                # (как в fish), дальше — листать
                r = resolve(self.wb, done, typed, self.app.ctl.shell_synonyms())
                if r.leaves and len(r.common) > len(done):
                    self._accept(r.common, r.rest)
                    return 'break'
                self._list_line = line
            self._cycle(1)
            return 'break'
        if not line.strip():                          # пустая строка — карусель кандидатов
            self._branches()
            return 'break'
        if done is None:
            return 'break'
        if typed.strip():
            r = resolve(self.wb, done, typed, self.app.ctl.shell_synonyms())
            if len(r.leaves) == 1:
                self._accept(r.leaves[0])
            elif r.leaves and len(r.common) > len(done):
                self._accept(r.common, r.rest)          # неиспользованные слова — дальше в строке
            elif r.leaves:
                self._show_list(self._rank(r.choices), 0)
                self._list_line = line
                self._track('ambiguous', count=len(r.choices))
            return 'break'
        self._branches()
        return 'break'

    def _enter(self, e):
        if not self.on():
            return None
        if self._replace and self.list_shown and self.selected >= 0:
            self._replace_level(self.choices[self.selected])
            return 'break'
        if self.list_shown and self.selected >= 0:
            self._accept(self.choices[self.selected])
            self._finish()
            return 'break'
        n, line, done, typed, _ = self._state()
        if not line.strip():
            self._fresh_prediction(n, line)
            if self.prediction is not None:     # Enter — подтвердить предсказание
                return 'break' if self._take_prediction(None) else None
            self.close()                    # пустая строка — обычный перенос; подсказка —
            self.tail.place_forget()        # на новую строку, когда перенос случится
            self.app.root.after_idle(self.update)
            return None
        if self._finish():
            return 'break'
        if done is not None and typed.strip():
            r = resolve(self.wb, done, typed, self.app.ctl.shell_synonyms())
            if len(r.leaves) == 1:
                self._accept(r.leaves[0])
                self._finish()
                return 'break'
        # нечего показать (строка не понята) — обычный перенос: строка останется
        # непонятой (предупреждение), но врач не застревает
        return 'break' if self._branches() else None

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
        n, line = self._line()
        self._list_line = line          # выбрали стрелкой — Tab дальше листает, не дополняет
        return 'break'

    def _keypress(self, e):
        if not self.on():
            return None
        if e.keysym not in ('Left', 'Right', 'Up', 'Down', 'Return', 'KP_Enter', 'Tab', 'Escape'):
            self._cancel_dwell()            # набор — не «намеренная остановка»
        if e.char == '?':                   # ветки уровня; в текст не вставляется
            self._stat['questions'] += 1
            self._branches()
            return 'break'
        if e.keysym == 'BackSpace':         # не отдельной привязкой: общая <KeyPress>
            return self._backspace(e)       # (счётчик набора 0.4) иначе не увидит Backspace
        return None

    def _keyrelease(self, e):
        if self.on() and e.keysym in ('Up', 'Down') and not self.list_shown:
            if self._line() != self._seen:   # курсор ушёл на другую строку — подсказка за ним
                self.update()
            return None
        if not self.on() or e.keysym in ('Up', 'Down', 'Tab', 'Return', 'KP_Enter', 'Escape',
                                         'question', 'Shift_L', 'Shift_R', 'Control_L',
                                         'Control_R', 'Left', 'Right'):
            return None
        if e.keysym != 'BackSpace':
            self._expanded = None
        if self.list_shown and self._list_line is not None and self._line()[1] == self._list_line:
            return None         # отпускание клавиш после ?/Tab (Shift раньше «7») — список не трогать
        if self._line() == self._seen:
            return None         # текст строки не менялся (Alt, Shift, раскладка, стрелки) — всё как было
        self.update()
        return None

    # ---------- стрелки по уровням (как в fish) ----------
    def _segments(self, line: str) -> list[tuple[int, int]]:
        """(начало, конец) каждого уровня строки."""
        out, pos = [], 0
        for part in line.split(SEP):
            out.append((pos, pos + len(part)))
            pos += len(part) + len(SEP)
        return out

    def _arrow(self, step: int, e):
        if not self.on() or (e is not None and e.state & (0x1 | 0x4)) or self.list_shown:
            return None
        n, line = self._line()
        if SEP not in line:
            return None
        col = int(self.text.index('insert').split('.')[1])
        starts = [a for a, _ in self._segments(line)]
        if step < 0:
            prev = [a for a in starts if a < col]
            target = prev[-1] if prev else 0
        else:
            nxt = [a for a in starts if a > col]
            target = nxt[0] if nxt else len(line)
        self.text.mark_set('insert', f'{n}.{target}')
        self.text.see('insert')
        self._cancel_dwell()
        self._dwell_job = self.app.root.after(self.dwell_ms, self._open_siblings)
        return 'break'

    def _cancel_dwell(self):
        if self._dwell_job is not None:
            try:
                self.app.root.after_cancel(self._dwell_job)
            except tk.TclError:
                pass
            self._dwell_job = None

    def _codes(self, line: str) -> list[str]:
        """Коды уровней строки, пока они находятся в дереве."""
        out: list[str] = []
        for part in line.split(SEP):
            part = ' '.join(part.split())
            hit = next((c for c in children_of(self.wb, out[-1] if out else None)
                        if ' '.join(c.text.split()) == part), None)
            if hit is None:
                break
            out.append(hit.id)
        return out

    def _open_siblings(self):
        """Курсор стоит на уровне — вниз раскрываются его соседи."""
        self._dwell_job = None
        if not self.on():
            return
        n, line = self._line()
        col = int(self.text.index('insert').split('.')[1])
        segs = self._segments(line)
        k = next((i for i, (a, b) in enumerate(segs) if a <= col <= b), None)
        codes = self._codes(line)
        if k is None or k >= len(codes):
            return
        parent = tuple(codes[:k])
        kids = children_of(self.wb, parent[-1] if parent else None)
        choices = self._rank([parent + (c.id,) for c in kids])
        sel = next(i for i, p in enumerate(choices) if p[-1] == codes[k])
        self._show_list(choices, sel)
        self._replace = (n, k)
        self._list_line = line          # открыт явно (остановкой) — Tab только листает

    def _replace_level(self, new: Path) -> bool:
        """Заменить уровень; уровни ниже — остаются, если такой же текст есть
        у нового родителя, иначе снимаются (строка ждёт Tab)."""
        n, k = self._replace
        line = self.text.get(f'{n}.0', f'{n}.end')
        tail = [' '.join(p.split()) for p in line.split(SEP)[k + 1:]]
        path = list(new)
        for part in tail:
            hit = next((c for c in children_of(self.wb, path[-1])
                        if ' '.join(c.text.split()) == part), None)
            if hit is None:
                break
            path.append(hit.id)
        self._set_line(n, self._path_text(tuple(path)))
        self.close()
        self._mark_ok()
        self._track('replace_level', depth=k + 1, kept=len(path) - k - 1)
        return True

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
