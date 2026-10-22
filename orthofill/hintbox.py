"""Подсказки у курсора в поле записи (как IntelliSense в VS Code).

Серый «хвост» лучшего слова — метка поверх текста после курсора (не вставка:
не попадает ни в отмену, ни в запись). Если слов несколько — список под строкой
(рамка в главном окне через place(), не отдельное окно). Tab — принять верхнее
или выбранное; Enter принимает, только если вошли в список стрелкой, иначе это
обычный перенос строки; Ctrl+Enter не перехватывается."""
from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont

_WORD_END = re.compile(r'[A-Za-zА-Яа-яЁё]+$')
_KIND = {'doctor': 'ваше слово', 'history': 'из ваших записей', 'item': 'пункт',
         'phrase': 'фраза', 'value': ''}
# команда фразы: «.имя» в начале строки или после пробела/запятой («нед.», «0.016» — нет)
_CMD = re.compile(r'(?:^|(?<=[\s,;]))\.([A-Za-zА-Яа-яЁё0-9]*)$')
_KEEP = {'Tab', 'Up', 'Down', 'Return', 'KP_Enter', 'Escape', 'Shift_L', 'Shift_R',
         'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'ISO_Next_Group', 'Caps_Lock'}
_SEL_BG, _BORDER = '#e3eef7', '#1f5f8b'
# движение курсора по готовому тексту — подсказку закрыть (→ не должна принимать
# подсказку к слову, мимо которого просто проходит курсор)
_NAV = {'Left', 'Right', 'Home', 'End', 'Prior', 'Next'}


class HintBox:
    def __init__(self, app, text: tk.Text):
        self.app, self.text = app, text
        self.items: list = []
        self.selected = -1            # −1 — в список не входили
        self.prefix = ''
        self.list_shown = False
        self._forced = False            # открыто Ctrl+Space: и с 1–2 букв
        self.phrase = ''                # серый хвост привычной фразы ('' — режим слов)
        self._phrase_at = ''            # текст до курсора, к которому этот хвост
        self._reopen = False            # Ctrl+→ взял слово — после отпускания показать остаток
        self._cmd = False               # подсказки — фразы по «.имя»
        self.fields: list[tuple[str, str, list[str]]] = []   # поля раскрытой фразы (метки, значения)
        self.field_i = -1
        text.tag_configure('field', background='#e3eef7')
        self._view = None
        self._size = None
        bg = text.cget('background')
        self.tail = tk.Label(text, text='', fg='#8a95a1', bg=bg, font=app.f_text,
                             bd=0, padx=0, pady=0)
        self.frame = tk.Frame(app.root, bg='#ffffff', highlightthickness=1,
                              highlightbackground='#c9ced4')
        text.bind('<KeyRelease>', self._on_key_release, add='+')
        for seq, fn in (('<Tab>', self._tab), ('<Down>', lambda e: self._move(1, e)),
                        ('<Up>', lambda e: self._move(-1, e)), ('<Return>', self._enter),
                        ('<Escape>', self._escape), ('<Control-space>', self._manual),
                        ('<Right>', self._right), ('<Control-Right>', self._ctrl_right)):
            text.bind(seq, fn)
        text.bind('<FocusOut>', lambda e: self.close(), add='+')
        text.bind('<Button-1>', lambda e: self.close(), add='+')
        # прокрутка поля — закрыть (список остался бы в чужом месте)
        self._yscroll = text.cget('yscrollcommand')
        text.configure(yscrollcommand=self._on_yscroll)
        app.root.bind('<Configure>', self._on_resize, add='+')

    # ---------- состояние ----------
    @property
    def visible(self) -> bool:
        return bool(self.items) or bool(self.phrase) or bool(self.fields)

    def _enabled(self) -> bool:
        return bool(self.app.hints_on.get())

    def close(self):
        if self.fields:
            self._end_fields()
        self._cmd = False
        self.items, self.selected, self.prefix, self._forced = [], -1, '', False
        self.phrase = self._phrase_at = ''
        self._reopen = False
        self.tail.configure(text='')
        self.tail.place_forget()
        self.frame.place_forget()
        self.list_shown = False

    def update(self, force: bool = False):
        """Подсказки к слову перед курсором (курсор — в конце слова)."""
        if not self._enabled():
            self.close()
            return
        if self.fields:                 # внутри раскрытой фразы: только подсветка полей
            self._refresh_fields()
            return
        t = self.text
        before = t.get('insert linestart', 'insert')
        after = t.get('insert', 'insert +1c')
        self.phrase = self._phrase_at = ''     # прежний хвост фразы — не тянуть дальше
        mc = _CMD.search(before)
        if mc and not (after and after.isalpha()):
            items = self.app.ctl.phrase_hints(mc.group(1))
            if items:
                self.close()
                self.prefix, self.items, self.selected, self._cmd = '.' + mc.group(1), items, -1, True
                t.see('insert')
                t.update_idletasks()
                self._view = t.yview()
                self._show()
                return
        # привычная фраза — только в конце строки (хвост не закрывает текст);
        # Ctrl+Space — явная просьба о словах: фразу пропустить
        if after in ('', '\n') and not force:
            cont = self.app.ctl.continuation(t.get('1.0', 'insert'))
            if cont:
                self.close()
                self.phrase, self._phrase_at = cont, t.get('1.0', 'insert')
                t.see('insert')
                t.update_idletasks()
                self._view = t.yview()
                self._show_phrase()
                return
        m = _WORD_END.search(before)
        if not m or (after and after.isalpha()):
            self.close()
            return
        items = self.app.ctl.hints(m.group(), force=force)
        if not items:
            self.close()
            return
        self.prefix, self.items, self.selected = m.group(), items, -1
        t.see('insert')                 # как при наборе: курсор виден
        t.update_idletasks()
        self._view = t.yview()
        self._show()

    # ---------- показ ----------
    def _show_phrase(self):
        """Хвост фразы — сколько помещается до края поля (по словам, с «…»);
        принимается ровно показанное."""
        t = self.text
        box = t.bbox('insert')
        if box is None:
            self.close()
            return
        self.frame.place_forget()
        self.list_shown = False
        font = tkfont.Font(font=self.tail.cget('font'))
        room = t.winfo_width() - box[0] - 12
        shown = self.phrase
        if font.measure(shown) > room:
            words = re.findall(r'\s*\S+', self.phrase)
            shown = ''
            for w in words:
                if font.measure(shown + w + '…') > room:
                    break
                shown += w
            if not shown.strip():
                self.close()
                return
            self.phrase = shown              # принять — только видимое
            shown += '…'
        self.tail.configure(text=shown)
        self.tail.place(x=box[0], y=box[1], bordermode='outside')

    def accept_phrase(self, one_word: bool = False) -> bool:
        """Принять хвост фразы целиком или одно следующее слово (Ctrl+→)."""
        t = self.text
        if not self.phrase or t.get('1.0', 'insert') != self._phrase_at:
            self.close()                    # текст изменился — хвост устарел
            return False
        chunk = re.match(r'\s*\S+', self.phrase).group() if one_word else self.phrase
        t.configure(autoseparators=False)   # одна отмена возвращает набранное
        t.edit_separator()
        t.insert('insert', chunk, ())
        t.edit_separator()
        t.configure(autoseparators=True)
        rest = self.phrase[len(chunk):]
        self.close()
        if one_word and rest.strip():
            self.phrase, self._phrase_at = rest, t.get('1.0', 'insert')
            self._reopen = True
            self._show_phrase()
        return True

    def _show(self):
        t = self.text
        box = t.bbox('insert')
        if box is None:
            self.close()
            return
        x, y, _, h = box
        top = self.items[max(self.selected, 0)]
        rest = top.word[len(self.prefix):] if top.word.lower().startswith(self.prefix.lower()) else ''
        self.tail.configure(text=rest)
        if rest:
            self.tail.place(x=x, y=y, bordermode='outside')
        else:
            self.tail.place_forget()
        if len(self.items) > 1 or not rest or self._cmd:   # без хвоста (и для фраз) — список:
            self._show_list(x, y, h)            # Tab не меняет текст «вслепую"
        else:
            self.frame.place_forget()
            self.list_shown = False

    def _show_list(self, x: int, y: int, h: int):
        f, t, root, app = self.frame, self.text, self.app.root, self.app
        for w in f.winfo_children():
            w.destroy()
        for i, hint in enumerate(self.items):
            sel = i == self.selected
            border = _BORDER if (i == 0 and self.selected < 0) else '#ffffff'
            row = tk.Frame(f, bg=_SEL_BG if sel else '#ffffff', highlightthickness=1,
                           highlightbackground=border, highlightcolor=border)
            row.pack(fill='x', padx=2, pady=(2 if i == 0 else 0, 0))
            bg = row.cget('bg')
            tk.Label(row, text=hint.word, font=app.f_text, bg=bg, padx=0).pack(side='left', padx=(6, 0))
            tk.Label(row, text=_KIND[hint.kind], font=app.f_small, fg='#8a95a1',
                     bg=bg).pack(side='right', padx=(8, 6))
            if hint.becomes:
                becomes = hint.becomes if len(hint.becomes) <= 80 else hint.becomes[:79] + '…'
                tk.Label(row, text=f'→ {becomes}', font=app.f_small, fg='#5f6b76',
                         bg=bg).pack(side='left', padx=(10, 0))
            for w in (row, *row.winfo_children()):
                w.bind('<Button-1>', lambda e, k=i: self.accept(k))
        foot = ('Tab — следующее поле · ↓ — выбрать · набор — своё · Esc — выйти' if self.fields
                else 'Tab — принять · ↓ — выбрать · Esc — закрыть')
        tk.Label(f, text=foot, font=app.f_small,
                 fg='#8a95a1', bg='#ffffff', anchor='w').pack(fill='x', padx=8, pady=(2, 3))
        width = t.winfo_width() if self.app.mode == 'narrow' else min(t.winfo_width(), 520)
        f.update_idletasks()
        fh = f.winfo_reqheight()
        rx = t.winfo_rootx() - root.winfo_rootx()
        ry = t.winfo_rooty() - root.winfo_rooty()
        left = rx if self.app.mode == 'narrow' else min(rx + x, rx + t.winfo_width() - width)
        below = ry + y + h + 2
        top = below if below + fh <= root.winfo_height() else max(0, ry + y - fh - 2)
        f.place(x=left, y=top, width=width)
        f.lift()
        self.list_shown = True

    # ---------- клавиши ----------
    def _prefix_here(self) -> bool:
        """Перед курсором всё ещё то начало слова, к которому подсказка
        (курсор могли сдвинуть, текст — отменить или вставить)."""
        t = self.text
        before = t.get('insert linestart', 'insert')
        after = t.get('insert', 'insert +1c')
        if self._cmd:
            return before.endswith(self.prefix) and not (after and after.isalpha())
        m = _WORD_END.search(before)
        return bool(m) and m.group() == self.prefix and not (after and after.isalpha())

    def accept(self, i: int | None = None) -> bool:
        if self.fields:                     # щелчок по значению поля
            return self._choose(self.selected if i is None else i)
        if not self.items:
            return False
        if not self._prefix_here():         # подсказка устарела — ничего не трогать
            self.close()
            return False
        hint = self.items[max(self.selected, 0) if i is None else i]
        if self._cmd:
            return self._expand(hint)
        t = self.text
        t.configure(autoseparators=False)   # одна отмена возвращает набранное
        t.edit_separator()
        t.delete(f'insert -{len(self.prefix)}c', 'insert')
        start = t.index('insert')
        t.insert('insert', hint.word, ())
        if hint.code:                       # слово с известным пунктом — токен
            self.app.bind_token(start, t.index('insert'), hint.code, hint.becomes)
        t.edit_separator()
        t.configure(autoseparators=True)
        self.close()
        return True

    # ---------- раскрытая фраза: поля ----------
    def _expand(self, hint) -> bool:
        """«.имя» → текст фразы; поля — между метками (набор остаётся внутри поля)."""
        from .phrases import field_spans, parse_template, render
        name = hint.word[1:]
        ph = next((p for p in self.app.ctl.workbook.phrases if p.name == name), None)
        if ph is None:
            self.close()
            return False
        parts = parse_template(ph.template)
        t = self.text
        t.configure(autoseparators=False)   # одна отмена возвращает «.имя»
        t.edit_separator()
        t.delete(f'insert -{len(self.prefix)}c', 'insert')
        start = t.index('insert')
        t.insert('insert', render(parts), ())
        t.edit_separator()
        t.configure(autoseparators=True)
        self.close()
        fields = []
        for k, (s, e) in enumerate(field_spans(parts)):
            ms, me = f'fld{k}s', f'fld{k}e'
            t.mark_set(ms, f'{start}+{s}c')
            t.mark_gravity(ms, 'left')
            t.mark_set(me, f'{start}+{e}c')
            t.mark_gravity(me, 'right')
            fields.append((ms, me, [v for v in parts if isinstance(v, list)][k]))
        self.app.ctl.count_phrase_use(name)
        if fields:
            self.fields = fields
            self._refresh_fields()
            self._activate_field(0)
        return True

    def _refresh_fields(self):
        t = self.text
        t.tag_remove('field', '1.0', 'end')
        for ms, me, _ in self.fields:
            t.tag_add('field', ms, me)

    def _activate_field(self, i: int):
        """Поле i: его текст выделен (набор заменит), список значений — у поля."""
        from .hints import Hint
        t = self.text
        self.field_i = i
        ms, me, values = self.fields[i]
        t.tag_remove('sel', '1.0', 'end')
        t.tag_add('sel', ms, me)
        t.mark_set('insert', me)
        self.items = [Hint(v, '', 'value') for v in values]
        self.selected = -1
        self._show_field_list()

    def _show_field_list(self):
        ms = self.fields[self.field_i][0]
        box = self.text.bbox(ms)
        self.tail.place_forget()
        if box is None:
            self.frame.place_forget()
            self.list_shown = False
            return
        self._show_list(box[0], box[1], box[3])

    def _choose(self, i: int) -> bool:
        """Выбрать значение текущего поля и перейти к следующему."""
        if not self.fields or i < 0 or i >= len(self.items):
            return False
        t = self.text
        ms, me, _ = self.fields[self.field_i]
        t.delete(ms, me)
        t.insert(ms, self.items[i].word, ())
        self._next_field()
        return True

    def _next_field(self):
        if self.field_i + 1 < len(self.fields):
            self._activate_field(self.field_i + 1)
        else:
            self._end_fields()

    def _end_fields(self):
        t = self.text
        t.tag_remove('field', '1.0', 'end')
        t.tag_remove('sel', '1.0', 'end')
        for ms, me, _ in self.fields:
            for m in (ms, me):
                try:
                    t.mark_unset(m)
                except tk.TclError:
                    pass
        self.fields, self.field_i = [], -1
        self.items, self.selected = [], -1
        self.frame.place_forget()
        self.list_shown = False

    def _on_key_release(self, e):
        if e.keysym in _NAV:
            if self._reopen and e.keysym == 'Right':    # отпустили Ctrl+→ — остаток виден
                self._reopen = False
                return
            self.close()
            return
        if e.keysym in _KEEP or e.keysym == 'space' and e.state & 0x4:
            return
        self.update(force=self._forced and bool(e.state & 0x4) is False)

    def _tab(self, e):
        if e is not None and e.state & (0x1 | 0x4):      # Shift/Ctrl+Tab — не наше
            return None
        if self.fields:
            self._next_field()
            return 'break'
        if self.phrase:
            return 'break' if self.accept_phrase() else None
        if self.items and (self.list_shown or self.tail.cget('text')) and self.accept():
            return 'break'
        return None

    def _move(self, step: int, e=None):
        if e is not None and e.state & (0x1 | 0x4):      # Shift/Ctrl+стрелки — не наше
            return None
        if self.fields and self.list_shown:
            self.selected = max(0, min(len(self.items) - 1, self.selected + step))
            self._show_field_list()
            return 'break'
        if not self.list_shown:             # только хвост: стрелка двигает курсор
            self.close()
            return None
        self.selected = max(0, min(len(self.items) - 1, self.selected + step))
        self._show()
        return 'break'

    def _enter(self, e):
        if self.fields:
            if self.selected >= 0 and self._choose(self.selected):
                return 'break'
            self._end_fields()
            return None
        if self.items and self.selected >= 0 and self.accept():
            return 'break'
        self.close()
        return None

    def _right(self, e):
        """→ принимает серый хвост (как в браузере и VS Code); иначе — курсор вправо."""
        if e is not None and e.state & (0x1 | 0x4):
            return None
        if self.phrase:
            return 'break' if self.accept_phrase() else None
        if self.items and self.tail.cget('text') and self.accept(0 if self.selected < 0 else None):
            return 'break'
        return None

    def _ctrl_right(self, e):
        """Ctrl+→ — одно слово привычной фразы (как в fish); иначе — как обычно."""
        if self.phrase and not (e is not None and e.state & 0x1):
            return 'break' if self.accept_phrase(one_word=True) else None
        return None

    def _escape(self, e):
        if self.items or self.phrase or self.fields:
            self.close()
            return 'break'
        return None

    def _manual(self, e):
        if not self._enabled():
            return None
        self._forced = True
        self.update(force=True)
        return 'break'

    # ---------- закрытие ----------
    def _on_yscroll(self, first, last):
        if self._yscroll:
            self.text.tk.call(*self._yscroll.split(), first, last)
        if self.visible and self._view is not None and (float(first), float(last)) != tuple(
                float(v) for v in self._view):
            self.close()

    def _on_resize(self, e):
        """Окно изменило размер (в т.ч. от живого протокола) — подсказку не
        закрывать, а поставить под курсор заново, когда раскладка уляжется."""
        if e.widget is not self.app.root:
            return
        size = (e.width, e.height)
        if size != self._size:
            self._size = size
            if self.phrase:
                self.app.root.after_idle(lambda: self.phrase and self._show_phrase())
            elif self.items:
                self.app.root.after_idle(lambda: self.items and self._show())
