"""Подсказки у курсора в поле записи (как IntelliSense в VS Code).

Серый «хвост» лучшего слова — метка поверх текста после курсора (не вставка:
не попадает ни в отмену, ни в запись). Если слов несколько — список под строкой
(рамка в главном окне через place(), не отдельное окно). Tab — принять верхнее
или выбранное; Enter принимает, только если вошли в список стрелкой, иначе это
обычный перенос строки; Ctrl+Enter не перехватывается."""
from __future__ import annotations

import re
import tkinter as tk

_WORD_END = re.compile(r'[A-Za-zА-Яа-яЁё]+$')
_KIND = {'doctor': 'ваше слово', 'history': 'из ваших записей', 'item': 'пункт'}
_KEEP = {'Tab', 'Up', 'Down', 'Return', 'KP_Enter', 'Escape', 'Shift_L', 'Shift_R',
         'Control_L', 'Control_R', 'Alt_L', 'Alt_R', 'ISO_Next_Group', 'Caps_Lock'}
_SEL_BG, _BORDER = '#e3eef7', '#1f5f8b'


class HintBox:
    def __init__(self, app, text: tk.Text):
        self.app, self.text = app, text
        self.items: list = []
        self.selected = -1            # −1 — в список не входили
        self.prefix = ''
        self.list_shown = False
        self._forced = False            # открыто Ctrl+Space: и с 1–2 букв
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
                        ('<Right>', self._right)):
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
        return bool(self.items)

    def _enabled(self) -> bool:
        return bool(self.app.hints_on.get())

    def close(self):
        self.items, self.selected, self.prefix, self._forced = [], -1, '', False
        self.tail.configure(text='')
        self.tail.place_forget()
        self.frame.place_forget()
        self.list_shown = False

    def update(self, force: bool = False):
        """Подсказки к слову перед курсором (курсор — в конце слова)."""
        if not self._enabled():
            self.close()
            return
        t = self.text
        before = t.get('insert linestart', 'insert')
        after = t.get('insert', 'insert +1c')
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
        if len(self.items) > 1 or not rest:     # без хвоста — список даже из одного:
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
                tk.Label(row, text=f'→ {hint.becomes[:48]}', font=app.f_small, fg='#5f6b76',
                         bg=bg).pack(side='left', padx=(10, 0))
            for w in (row, *row.winfo_children()):
                w.bind('<Button-1>', lambda e, k=i: self.accept(k))
        tk.Label(f, text='Tab — принять · ↓ — выбрать · Esc — закрыть', font=app.f_small,
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
        m = _WORD_END.search(t.get('insert linestart', 'insert'))
        after = t.get('insert', 'insert +1c')
        return bool(m) and m.group() == self.prefix and not (after and after.isalpha())

    def accept(self, i: int | None = None) -> bool:
        if not self.items:
            return False
        if not self._prefix_here():         # подсказка устарела — ничего не трогать
            self.close()
            return False
        hint = self.items[max(self.selected, 0) if i is None else i]
        t = self.text
        t.configure(autoseparators=False)   # одна отмена возвращает набранное
        t.edit_separator()
        t.delete(f'insert -{len(self.prefix)}c', 'insert')
        t.insert('insert', hint.word)
        t.edit_separator()
        t.configure(autoseparators=True)
        self.close()
        return True

    def _on_key_release(self, e):
        if e.keysym in _KEEP or e.keysym == 'space' and e.state & 0x4:
            return
        self.update(force=self._forced and bool(e.state & 0x4) is False)

    def _tab(self, e):
        if e is not None and e.state & (0x1 | 0x4):      # Shift/Ctrl+Tab — не наше
            return None
        if self.items and (self.list_shown or self.tail.cget('text')) and self.accept():
            return 'break'
        return None

    def _move(self, step: int, e=None):
        if e is not None and e.state & (0x1 | 0x4):      # Shift/Ctrl+стрелки — не наше
            return None
        if not self.list_shown:             # только хвост: стрелка двигает курсор
            self.close()
            return None
        self.selected = max(0, min(len(self.items) - 1, self.selected + step))
        self._show()
        return 'break'

    def _enter(self, e):
        if self.items and self.selected >= 0 and self.accept():
            return 'break'
        self.close()
        return None

    def _right(self, e):
        """→ принимает серый хвост (как в браузере и VS Code); иначе — курсор вправо."""
        if e is not None and e.state & (0x1 | 0x4):
            return None
        if self.items and self.tail.cget('text') and self.accept(0 if self.selected < 0 else None):
            return 'break'
        return None

    def _escape(self, e):
        if self.items:
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
        if self.items and self._view is not None and (float(first), float(last)) != tuple(
                float(v) for v in self._view):
            self.close()

    def _on_resize(self, e):
        if e.widget is not self.app.root:
            return
        size = (e.width, e.height)
        if size != self._size:
            self._size = size
            self.close()
