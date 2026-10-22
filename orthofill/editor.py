"""Окно редактора пресета: слева дерево «раздел → группа → вариант» с поиском,
справа свойства выбранного. Вся логика — в Draft (orthofill/draft.py); окно
только показывает и передаёт команды. После каждой команды сверка эталонов и
проверка классификатора пересчитываются сами (живой счётчик внизу)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from .addition import row_text, search_items
from .lint import lint
from .methods import METHOD_LABELS, WHEN_LABELS
from .ui import ACCENT, MUTED, TITLE, WARN_TEXT

_KIND = {'section': 'Раздел', 'group': 'Группа', 'variant': 'Вариант', 'single': 'Пункт'}
_NO_DEFAULT = '— не выводить, если врач не написал —'
_RULE_DEFAULT = '— как решит правило —'


def _ws(text: str) -> str:
    return ' '.join(text.split())


class EditorWindow:
    def __init__(self, app, select: str | None = None):
        self.app, self.ctl = app, app.ctl
        self.draft = self.ctl.open_draft()
        self._hits: list[str] = []
        self._hit = 0
        self.findings = []
        self.top = top = tk.Toplevel(app.root)
        top.title(f'{TITLE} — пресет «{self.draft.wb.name}»')
        top.geometry('1040x680')
        top.minsize(560, 480)
        top.protocol('WM_DELETE_WINDOW', self.close)
        self._build()
        self.refresh()
        self.select(select or (self.draft.wb.items[0].id if self.draft.wb.items else None))

    # ---------- построение ----------
    def _build(self):
        app, top = self.app, self.top
        top.update_idletasks()
        head = ttk.Frame(top, padding=(14, 10, 14, 4))
        head.pack(fill='x')
        ttk.Label(head, text=self.draft.wb.name, font=app.f_title).pack(side='left')
        self.head_right = ttk.Frame(head)
        self.head_right.pack(side='right')

        self.bottom = bottom = ttk.Frame(top, padding=(14, 6, 14, 10))
        bottom.pack(fill='x', side='bottom')
        self.undo_btn = ttk.Button(bottom, text='↶ Отменить', command=self.undo)
        self.undo_btn.pack(side='left')
        self.redo_btn = ttk.Button(bottom, text='↷ Вернуть', command=self.redo)
        self.redo_btn.pack(side='left', padx=(6, 0))
        self.changed_lbl = ttk.Label(bottom, text='', foreground=WARN_TEXT)
        self.changed_lbl.pack(side='left', padx=(12, 0))
        self.status_lbl = ttk.Label(bottom, text='', foreground=MUTED)
        self.status_lbl.pack(side='left', padx=(12, 0))
        self.bottom_right = ttk.Frame(bottom)
        self.bottom_right.pack(side='right')

        self.notebook = nb = ttk.Notebook(top)
        nb.pack(fill='both', expand=True, padx=14)
        items_tab = ttk.Frame(nb, padding=(0, 8, 0, 0))
        nb.add(items_tab, text='Пункты протокола')

        narrow = app.root.winfo_width() < 760 and app.root.winfo_width() > 1
        pane = ttk.PanedWindow(items_tab, orient='vertical' if narrow else 'horizontal')
        pane.pack(fill='both', expand=True)
        left = ttk.Frame(pane)
        self.props = ttk.Frame(pane, padding=(12, 0, 0, 0))
        pane.add(left, weight=3)
        pane.add(self.props, weight=2)
        self.pane = pane
        if not narrow:      # дереву — больше места: тексты пунктов длинные
            def place_sash(e=None):
                if top.winfo_width() > 1:
                    pane.sashpos(0, int(top.winfo_width() * 0.58))
                    top.unbind('<Map>')
                    self._show_props()      # иначе подписи справа не перерисовываются
            top.bind('<Map>', place_sash)
            top.after(200, place_sash)

        sr = ttk.Frame(left)
        sr.pack(fill='x', pady=(0, 6))
        ttk.Label(sr, text='Найти:').pack(side='left')
        self.search = ttk.Entry(sr)
        self.search.pack(side='left', fill='x', expand=True, padx=(6, 0))
        self.search.bind('<KeyRelease>', lambda e: None if e.keysym in ('Return', 'Down', 'Up')
                         else self._on_search())
        self.search.bind('<Return>', lambda e: self._next_hit())
        self.search.bind('<Down>', lambda e: self._next_hit())

        btns = ttk.Frame(left)          # снизу — видны и в узком окне
        btns.pack(fill='x', side='bottom', pady=(6, 0))
        tf = ttk.Frame(left)
        tf.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(tf, columns=('code',), selectmode='browse')
        self.tree.heading('#0', text='Пункт')
        self.tree.column('#0', width=240, minwidth=160, stretch=True)
        self.tree.heading('code', text='Код')
        self.tree.column('code', width=64, stretch=False, anchor='w')
        sb = ttk.Scrollbar(tf, orient='vertical', command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side='left', fill='both', expand=True)
        sb.pack(side='right', fill='y')
        self.tree.bind('<<TreeviewSelect>>', lambda e: self._show_props())
        self.tree.tag_configure('finding', foreground=WARN_TEXT)
        self.tree.tag_configure('section', font=app.f_label)

        for text, cmd in (('+ Пункт', self.add_item), ('+ Вариант', self.add_variant),
                          ('↑', lambda: self.move(-1)), ('↓', lambda: self.move(1)),
                          ('Удалить', self.delete_selected)):
            ttk.Button(btns, text=text, command=cmd).pack(side='left', padx=(0, 6))

    # ---------- дерево ----------
    def _kind(self, code: str) -> str:
        it = self.draft.wb.by_id[code]
        if it.level == 1:
            return 'section'
        if it.children:
            return 'group'
        return 'variant' if it.level == 3 and not it.orphan else 'single'

    def _label(self, code: str, flagged: set[str]) -> str:
        wb = self.draft.wb
        it = wb.by_id[code]
        text = _ws(it.text)
        if len(text) > 90:
            text = text[:89] + '…'
        if it.children and it.level == 2:
            text += f'  ({len(it.children)})'
        parent = wb.by_id.get(it.parent) if it.parent else None
        if parent is not None and parent.default == code:
            text += '  ●'
        if it.when == 'always':
            text += '  · всегда'
        if code in flagged:
            text = '⚠ ' + text
        return text

    def refresh(self):
        """Дерево заново (выделение и раскрытые узлы — как были), сверка, проверка."""
        tree, wb = self.tree, self.draft.wb
        sel = tree.selection()
        opened = {i for i in self._all_nodes() if tree.item(i, 'open')}
        self.findings = lint(wb)
        flagged = {c for f in self.findings for c in f.code.split(',')}
        tree.delete(*tree.get_children())
        for it in wb.items:
            parent = it.parent if it.parent in wb.by_id else ''
            tree.insert(parent, 'end', iid=it.id, text=self._label(it.id, flagged),
                        values=(it.id,), open=it.id in opened,
                        tags=('section',) if it.level == 1 else
                        ('finding',) if it.id in flagged else ())
        if sel and tree.exists(sel[0]):
            self._focus(sel[0])
        results = self.draft.check()
        ok = sum(r.ok for r in results)
        self.results = results
        self.status_lbl.configure(
            text=f'эталоны {ok}/{len(results)} · находок {len(self.findings)}',
            foreground='#1f7a3f' if ok == len(results) and not self.findings else WARN_TEXT)
        n = self.draft.changed
        self.changed_lbl.configure(text=f'● Изменено: {n}, не сохранено' if n else '')
        self.undo_btn.state(['!disabled'] if self.draft.can_undo else ['disabled'])
        self.redo_btn.state(['!disabled'] if self.draft.can_redo else ['disabled'])

    def _all_nodes(self):
        stack = list(self.tree.get_children())
        while stack:
            i = stack.pop()
            yield i
            stack += self.tree.get_children(i)

    def _focus(self, code: str):
        tree = self.tree
        p = tree.parent(code)
        while p:
            tree.item(p, open=True)
            p = tree.parent(p)
        tree.selection_set(code)
        tree.focus(code)
        tree.see(code)

    def select(self, code: str | None):
        if code and self.tree.exists(code):
            self._focus(code)
            self._show_props()

    def selected(self) -> str | None:
        s = self.tree.selection()
        return s[0] if s else None

    # ---------- поиск ----------
    def _on_search(self):
        q = self.search.get().strip()
        self._hits = [h.code for h in search_items(self.draft.wb, q, limit=50)] if q else []
        self._hit = 0
        if self._hits:
            self.select(self._hits[0])

    def _next_hit(self):
        if self._hits:
            self._hit = (self._hit + 1) % len(self._hits)
            self.select(self._hits[self._hit])
        return 'break'

    # ---------- команды ----------
    def _done(self, select: str | None = None):
        self.refresh()
        self.select(select if select and self.tree.exists(select) else self.selected())

    def undo(self):
        self.draft.undo()
        self._done()

    def redo(self):
        self.draft.redo()
        self._done()

    def add_item(self):
        """Новая группа/пункт раздела — после выделенной группы (или в конец раздела)."""
        code = self.selected()
        if code is None:
            return
        wb = self.draft.wb
        it = wb.by_id[code]
        section = code[0]
        after = None if it.level == 1 else (it.id if it.level == 2 else it.parent)
        new = self.draft.add(section, after, 'Новый пункт', 2)
        self._done(new)
        self._edit_text_soon()

    def add_variant(self):
        """Новый вариант — после выделенного варианта или в конец выделенной группы."""
        code = self.selected()
        if code is None or self._kind(code) == 'section':
            return
        it = self.draft.wb.by_id[code]
        group, after = (it.parent, code) if self._kind(code) == 'variant' else (code, None)
        new = self.draft.add(group, after, 'Новый вариант', 3)
        self._done(new)
        self._edit_text_soon()

    def move(self, delta: int):
        code = self.selected()
        if code and self.draft.move(code, delta):
            self._done(code)

    def delete_selected(self, confirm: bool = True):
        code = self.selected()
        if code is None:
            return
        it = self.draft.wb.by_id[code]
        if confirm:
            refs, words = self.draft.impact(code)
            extra = []
            if refs:
                extra.append(f'есть в эталонах: {refs}')
            if words:
                extra.append(f'слов врача: {words} (будут удалены)')
            what = ' с вариантами' if it.children else ''
            text = f'Удалить «{_ws(it.text)[:60]}»{what}?'
            if extra:
                text += '\n\n' + '; '.join(extra) + '.\nЭталоны с этим пунктом перестанут совпадать.'
            if self.app._choice('Удалить пункт', text,
                                [('delete', 'Удалить'), ('cancel', 'Отмена')]) != 'delete':
                return
        nxt = self.tree.next(code) or self.tree.prev(code) or self.tree.parent(code)
        self.draft.delete(code)
        self._done(nxt or None)

    # ---------- свойства ----------
    def _clear_props(self):
        for w in self.props.winfo_children():
            w.destroy()

    def _show_props(self):
        self._clear_props()
        code = self.selected()
        if code is None:
            return
        wb, app, p = self.draft.wb, self.app, self.props
        it = wb.by_id[code]
        kind = self._kind(code)
        ttk.Label(p, text=_KIND[kind], font=app.f_label, foreground=MUTED).pack(anchor='w')

        # код
        row = ttk.Frame(p)
        row.pack(fill='x', pady=(4, 0))
        ttk.Label(row, text='Код:').pack(side='left')
        self.code_entry = ttk.Entry(row, width=8)
        self.code_entry.insert(0, code)
        self.code_entry.pack(side='left', padx=(6, 0))
        self.code_entry.bind('<Return>', lambda e: self.commit_code())
        self.code_entry.bind('<FocusOut>', lambda e: self.commit_code())
        if kind in ('section', 'group'):
            ttk.Button(row, text='Перенумеровать по порядку',
                       command=lambda: self._renumber(code)).pack(side='left', padx=(10, 0))
        self.code_err = ttk.Label(p, text='', foreground=WARN_TEXT, wraplength=360)
        self.code_err.pack(anchor='w')

        # текст
        ttk.Label(p, text='Название' if kind in ('section', 'group') else 'Текст в протоколе',
                  font=app.f_small).pack(anchor='w', pady=(6, 0))
        self.text_box = tk.Text(p, height=4, wrap='word', font=app.f_text, relief='solid',
                                borderwidth=1, highlightthickness=0, padx=6, pady=4)
        self.text_box.insert('1.0', it.text)
        self.text_box.pack(fill='x')
        self.text_box.bind('<Return>', lambda e: (self.commit_text(), 'break')[1])
        self.text_box.bind('<FocusOut>', lambda e: self.commit_text())

        if kind == 'group':
            from .engine import _guess_kind
            ttk.Label(p, text='Как выбирать вариант', font=app.f_small).pack(anchor='w', pady=(10, 0))
            key = it.method or _guess_kind(it) or 'words'
            self.method_var = tk.StringVar(value=METHOD_LABELS.get(key, key))
            cb = ttk.Combobox(p, textvariable=self.method_var, state='readonly',
                              values=list(METHOD_LABELS.values()))
            cb.pack(fill='x')
            cb.bind('<<ComboboxSelected>>', lambda e: self._on_method())
            ttk.Label(p, text=f'{key} · {"задано" if it.method else "угадано по названию"}',
                      font=app.f_small, foreground=MUTED).pack(anchor='w')

            ttk.Label(p, text='Если врач не написал', font=app.f_small).pack(anchor='w', pady=(10, 0))
            self._variant_by_label = {_ws(c.text): c.id for c in it.children}
            # без умолчания группа «по словам» не выводится, а встроенное правило
            # (гигиена, этап…) решит само
            none = _NO_DEFAULT if key == 'words' else _RULE_DEFAULT
            cur = next((_ws(c.text) for c in it.children if c.id == it.default), none)
            self.default_var = tk.StringVar(value=cur)
            cb = ttk.Combobox(p, textvariable=self.default_var, state='readonly',
                              values=[none] + list(self._variant_by_label))
            cb.pack(fill='x')
            cb.bind('<<ComboboxSelected>>', lambda e: self._on_default())
        elif kind == 'single':
            from .engine import _effective_when
            ttk.Label(p, text='Когда в протоколе', font=app.f_small).pack(anchor='w', pady=(10, 0))
            key = it.when or _effective_when(wb).get(code, 'mentioned')
            self.when_var = tk.StringVar(value=WHEN_LABELS[key])
            cb = ttk.Combobox(p, textvariable=self.when_var, state='readonly',
                              values=list(WHEN_LABELS.values()))
            cb.pack(fill='x')
            cb.bind('<<ComboboxSelected>>', lambda e: self._on_when())
            if not it.when:
                ttk.Label(p, text='угадано по эталонам', font=app.f_small,
                          foreground=MUTED).pack(anchor='w')

        if kind != 'section':
            ttk.Label(p, text='Слова упоминания (через запятую)',
                      font=app.f_small).pack(anchor='w', pady=(10, 0))
            self.words_entry = ttk.Entry(p)
            self.words_entry.insert(0, ', '.join(it.words))
            self.words_entry.pack(fill='x')
            self.words_entry.bind('<Return>', lambda e: self._on_words())
            self.words_entry.bind('<FocusOut>', lambda e: self._on_words())
            taught = [e.word for e in wb.dictionary
                      if e.code == code or (not e.code and _ws(e.item_text) == _ws(it.text))]
            if taught:
                ttk.Label(p, text='Слова врача: ' + ', '.join(taught), font=app.f_small,
                          foreground=MUTED, wraplength=360).pack(anchor='w', pady=(4, 0))

            group = wb.by_id.get(it.parent) if kind == 'variant' else None
            ttk.Label(p, text='Так будет в протоколе', font=app.f_small).pack(anchor='w', pady=(10, 0))
            ttk.Label(p, text=row_text(it, group), wraplength=360, foreground=ACCENT,
                      justify='left').pack(anchor='w')

        subtree = {i.id for i in wb.items if i.id.startswith(code)}
        used = sum(any(c in subtree for c, _ in r.lines) for r in wb.references)
        ttk.Label(p, text=f'есть в эталонах: {used} из {len(wb.references)}', font=app.f_small,
                  foreground=MUTED).pack(anchor='w', pady=(10, 0))

    def _edit_text_soon(self):
        self.top.after_idle(lambda: (self.text_box.focus_set(),
                                     self.text_box.tag_add('sel', '1.0', 'end-1c')))

    def text_field(self) -> str:
        return self.text_box.get('1.0', 'end-1c')

    def set_text_field(self, text: str):
        self.text_box.delete('1.0', 'end')
        self.text_box.insert('1.0', text)

    def commit_text(self):
        code = self.selected()
        if code is None or not self.text_box.winfo_exists():
            return
        text = _ws(self.text_field())
        if text and text != _ws(self.draft.wb.by_id[code].text):
            self.draft.set_text(code, text)
            self._done(code)

    def set_code_field(self, code: str):
        self.code_entry.delete(0, 'end')
        self.code_entry.insert(0, code)

    def commit_code(self):
        code = self.selected()
        if code is None or not self.code_entry.winfo_exists():
            return
        new = self.code_entry.get().strip().lower()
        if new == code:
            return
        err = self.draft.set_code(code, new)
        if err and 'уже занят' in err and len(new) == len(code) and new[:-1] == code[:-1] \
                or err and 'уже занят' in err and len(code) > 2 and new[:2] == code[:2]:
            other = _ws(self.draft.wb.by_id[new].text)[:50]
            ans = self.app._choice('Код занят', f'Код «{new}» уже у «{other}».\n\n'
                                   f'Поменять коды местами?',
                                   [('swap', 'Поменять местами'), ('cancel', 'Отмена')])
            if ans != 'swap':
                return
            self.draft.swap(code, new)
            err = None
        if err:
            self.code_err.configure(text=err)
            return
        self._done(new)

    def _renumber(self, code: str):
        self.draft.renumber(code)
        self._done(code)

    def _on_method(self):
        code = self.selected()
        key = next(k for k, v in METHOD_LABELS.items() if v == self.method_var.get())
        self.draft.set_prop(code, 'method', key)
        self._done(code)

    def _on_default(self):
        code = self.selected()
        self.draft.set_prop(code, 'default', self._variant_by_label.get(self.default_var.get()))
        self._done(code)

    def _on_when(self):
        code = self.selected()
        key = next(k for k, v in WHEN_LABELS.items() if v == self.when_var.get())
        self.draft.set_prop(code, 'when', key)
        self._done(code)

    def _on_words(self):
        code = self.selected()
        if code is None or not self.words_entry.winfo_exists():
            return
        words = [w.strip() for w in self.words_entry.get().split(',') if w.strip()]
        if words != self.draft.wb.by_id[code].words:
            self.draft.set_prop(code, 'words', words)
            self._done(code)

    # ---------- закрытие ----------
    def close(self):
        self.top.destroy()
