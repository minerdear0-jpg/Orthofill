"""Окно редактора пресета: слева дерево «раздел → группа → вариант» с поиском,
справа свойства выбранного. Вся логика — в Draft (orthofill/draft.py); окно
только показывает и передаёт команды. После каждой команды сверка эталонов и
проверка классификатора пересчитываются сами (живой счётчик внизу)."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from pathlib import Path
from tkinter import filedialog

from .addition import row_text, search_items
from .codes import inside
from .lint import JAW_FIX, LEVEL_LABELS
from .logic import format as format_condition, is_simple, refs as condition_refs
from .lint import lint
from .methods import METHOD_LABELS, WHEN_LABELS
from .ui import ACCENT, MUTED, TITLE, WARN_TEXT

_KIND = {'section': 'Раздел', 'group': 'Группа', 'variant': 'Вариант', 'single': 'Пункт'}
_NO_DEFAULT = '— не выводить, если врач не написал —'
_RULE_DEFAULT = '— как решит правило —'
_COMBINE = {None: 'ИЛИ — один вариант', 'and': 'И — все упомянутые варианты'}
_JOIN = {'all': 'все строки', 'any': 'любая строка'}
_MENTIONED = 'упомянут'


class _CondRow:
    """Строка условия в окне: ☐ НЕ · поле · значение · ✕."""

    def __init__(self, not_var, field_var, value_var, value_cb):
        self.not_var, self.field_var, self.value_var, self.value_cb = \
            not_var, field_var, value_var, value_cb


def _short_variants(group) -> dict[str, str]:
    """Вариант → текст без общего начала соседей и точки: «вестибулярная
    лигатурная.» → «лигатурная» (чтобы список значений не обрезался)."""
    texts = [_ws(c.text).split() for c in group.children]
    common = 0
    while texts and all(len(t) > common + 1 and t[common].lower() == texts[0][common].lower()
                        for t in texts):
        common += 1
    return {c.id: ' '.join(t[common:]).rstrip('.:;, ') or _ws(c.text)
            for c, t in zip(group.children, texts)}


def _ws(text: str) -> str:
    return ' '.join(text.split())


class EditorWindow:
    def __init__(self, app, select: str | None = None):
        self.app, self.ctl = app, app.ctl
        self.draft = self.ctl.open_draft()
        self._hits: list[str] = []
        self._hit = 0
        self._props_code: str | None = None     # чьи поля сейчас справа
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
        self.bottom_right = ttk.Frame(bottom)      # первым — в узком окне не вытесняется
        self.bottom_right.pack(side='right')
        self.undo_btn = ttk.Button(bottom, text='↶ Отменить', command=self.undo)
        self.undo_btn.pack(side='left')
        self.redo_btn = ttk.Button(bottom, text='↷ Вернуть', command=self.redo)
        self.redo_btn.pack(side='left', padx=(6, 0))
        self.changed_lbl = ttk.Label(bottom, text='', foreground=WARN_TEXT)
        self.changed_lbl.pack(side='left', padx=(12, 0))
        self.status_lbl = ttk.Label(bottom, text='', foreground=MUTED)
        self.status_lbl.pack(side='left', padx=(12, 0))
        ttk.Button(self.bottom_right, text='Отменить изменения',
                   command=self.discard).pack(side='left')
        ttk.Button(self.bottom_right, text='Сохранить', style='Accent.TButton',
                   command=self.save).pack(side='left', padx=(6, 0))
        ttk.Button(self.head_right, text='Импорт xlsx…', command=self.import_xlsx).pack(side='left')
        ttk.Button(self.head_right, text='Экспорт xlsx…',
                   command=self.export_xlsx).pack(side='left', padx=(6, 0))
        top.bind('<Control-KeyPress>', self._on_ctrl)

        self.notebook = nb = ttk.Notebook(top)
        nb.pack(fill='both', expand=True, padx=14)
        items_tab = ttk.Frame(nb, padding=(0, 8, 0, 0))
        nb.add(items_tab, text='Пункты протокола')

        narrow = app.root.winfo_width() < 760 and app.root.winfo_width() > 1
        pane = ttk.PanedWindow(items_tab, orient='vertical' if narrow else 'horizontal')
        pane.pack(fill='both', expand=True)
        left = ttk.Frame(pane)
        right = ttk.Frame(pane)
        pane.add(left, weight=3)
        pane.add(right, weight=2)
        # свойства — с прокруткой: с условием и парами они не помещаются на 560 px
        bg = ttk.Style().lookup('TFrame', 'background') or '#fafafa'
        self.props_canvas = cv = tk.Canvas(right, highlightthickness=0, borderwidth=0,
                                           background=bg, width=360)
        psb = ttk.Scrollbar(right, orient='vertical', command=cv.yview)
        cv.configure(yscrollcommand=psb.set)
        psb.pack(side='right', fill='y')
        cv.pack(side='left', fill='both', expand=True)
        self.props = ttk.Frame(cv, padding=(12, 0, 8, 8))
        win_id = cv.create_window(0, 0, window=self.props, anchor='nw')
        self.props.bind('<Configure>', lambda e: cv.configure(scrollregion=cv.bbox('all')))
        cv.bind('<Configure>', lambda e: cv.itemconfigure(win_id, width=e.width))
        for w in (cv, self.props):
            w.bind('<Enter>', lambda e: cv.bind_all('<MouseWheel>', self._on_wheel))
            w.bind('<Leave>', lambda e: cv.unbind_all('<MouseWheel>'))
        self.pane = pane
        # ширины заданы заранее (дерево ~610 px из 1040, свойства — остальное):
        # двигать разделитель после показа ненадёжно — подписи справа не перерисовывались

        sr = ttk.Frame(left)
        sr.pack(fill='x', pady=(0, 6))
        ttk.Label(sr, text='Найти:').pack(side='left')
        self.search = ttk.Entry(sr)
        self.search.pack(side='left', fill='x', expand=True, padx=(6, 0))
        self.search.bind('<KeyRelease>', lambda e: None if e.keysym in ('Return', 'Down', 'Up')
                         else self._on_search())
        self.logic_only = tk.BooleanVar(value=False)
        ttk.Checkbutton(sr, text='только с логикой', variable=self.logic_only,
                        command=self.refresh).pack(side='left', padx=(8, 0))
        self.search.bind('<Return>', lambda e: self._next_hit())
        self.search.bind('<Down>', lambda e: self._next_hit())

        btns = ttk.Frame(left)          # снизу — видны и в узком окне
        btns.pack(fill='x', side='bottom', pady=(6, 0))
        tf = ttk.Frame(left)
        tf.pack(fill='both', expand=True)
        self.tree = ttk.Treeview(tf, columns=('code', 'logic'), selectmode='browse')
        self.tree.heading('#0', text='Пункт')
        self.tree.column('#0', width=300, minwidth=160, stretch=True)
        self.tree.heading('code', text='Код')
        self.tree.column('code', width=56, stretch=False, anchor='w')
        self.tree.heading('logic', text='Логика')
        self.tree.column('logic', width=64, stretch=False, anchor='w')
        self.tree.tag_configure('broken', foreground=WARN_TEXT)
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

        self.refs_page, self.refs_tab = self._tab_tree(
            'Эталоны', (('Принять новое как эталон', self.accept_reference),
                        ('Удалить эталон', self.delete_reference)), columns=())
        self.words_page, self.words_tab = self._tab_tree(
            'Слова врача', (('Удалить слово', self.delete_word),),
            columns=(('item', 'Пункт', 360), ('code', 'Код', 60),
                     ('added', 'Добавлено', 100), ('hits', 'Сработало', 80)))
        self.words_tab.heading('#0', text='Слово')
        self.words_tab.bind('<Double-1>', lambda e: self._goto(
            self.words_tab.set(self.words_tab.focus(), 'code')))
        self.lint_page, self.lint_tab = self._tab_tree(
            'Проверка', (('Поменять коды местами', self._fix_selected),), columns=(('level', 'Вид', 150),))
        self.lint_tab.heading('#0', text='Находка')
        self.lint_tab.bind('<Double-1>', lambda e: self._goto(
            (self.lint_tab.focus() or '').split('|')[-1].split(',')[0]))

    def _tab_tree(self, title, buttons, columns):
        page = ttk.Frame(self.notebook, padding=(0, 8, 0, 0))
        self.notebook.add(page, text=title)
        row = ttk.Frame(page)
        row.pack(fill='x', side='bottom', pady=(6, 0))
        for text, cmd in buttons:
            ttk.Button(row, text=text, command=cmd).pack(side='left', padx=(0, 6))
        tree = ttk.Treeview(page, columns=[c[0] for c in columns], selectmode='browse',
                            show='tree headings' if columns else 'tree')
        tree.column('#0', width=420, stretch=True)
        for key, head, width in columns:
            tree.heading(key, text=head)
            tree.column(key, width=width, stretch=False)
        tree.pack(fill='both', expand=True)
        tree.tag_configure('bad', foreground=WARN_TEXT)
        return page, tree

    def _goto(self, code: str):
        if code and self.tree.exists(code):
            self.notebook.select(0)
            self.select(code)

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
        badges = {it.id: self._badge(it) for it in wb.items}
        keep = None
        if self.logic_only.get():       # только пункты с логикой (и их родители)
            keep = set()
            for c, b in badges.items():
                while b and c and c not in keep:
                    keep.add(c)
                    c = wb.by_id[c].parent
        for it in wb.items:
            if keep is not None and it.id not in keep:
                continue
            parent = it.parent if it.parent in wb.by_id else ''
            badge = badges[it.id]
            tree.insert(parent, 'end', iid=it.id, text=self._label(it.id, flagged),
                        values=(it.id, badge), open=it.id in opened or keep is not None,
                        tags=('section',) if it.level == 1 else
                        ('broken',) if badge.startswith('⚠') else
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
        self._refresh_tabs()
        self.undo_btn.state(['!disabled'] if self.draft.can_undo else ['disabled'])
        self.redo_btn.state(['!disabled'] if self.draft.can_redo else ['disabled'])

    def _refresh_tabs(self):
        wb, nb = self.draft.wb, self.notebook
        t = self.refs_tab
        t.delete(*t.get_children())
        raws = {r.case_id: r.raw for r in wb.references}
        for r in self.results:
            iid = f'ref:{r.case_id}'
            t.insert('', 'end', iid=iid, open=not r.ok, tags=() if r.ok else ('bad',),
                     text=f'{"✓" if r.ok else "✗"} эталон {r.case_id}: {_ws(raws.get(r.case_id, ""))[:90]}')
            for code, text in r.missing:
                t.insert(iid, 'end', text=f'нет: {_ws(text)[:90]}  ({code})')
            for code, text in r.extra:
                t.insert(iid, 'end', text=f'лишнее: {_ws(text)[:90]}  ({code})')
            if not r.ok and not r.missing and not r.extra:
                t.insert(iid, 'end', text='отличается порядок строк')
        nb.tab(self.refs_page, text=f'Эталоны ({len(self.results)})')

        t = self.words_tab
        t.delete(*t.get_children())
        for e in wb.dictionary:
            t.insert('', 'end', iid=f'w:{e.word}', text=e.word,
                     values=(_ws(e.item_text)[:80], e.code, (e.added or '')[:10], e.hits))
        nb.tab(self.words_page, text=f'Слова врача ({len(wb.dictionary)})')

        t = self.lint_tab
        t.delete(*t.get_children())
        for k, f in enumerate(self.findings):
            t.insert('', 'end', iid=f'{k}|{f.code}', text=f.message, values=(LEVEL_LABELS[f.level],),
                     tags=('bad',) if f.level == 'error' else ())
        nb.tab(self.lint_page, text=f'Проверка ({len(self.findings)})')

    # ---------- вкладки: действия ----------
    def _selected_case(self) -> str | None:
        sel = self.refs_tab.selection()
        while sel and self.refs_tab.parent(sel[0]):
            sel = (self.refs_tab.parent(sel[0]),)
        return sel[0].split(':', 1)[1] if sel else None

    def accept_reference(self):
        case = self._selected_case()
        if case:
            self.draft.accept_reference(case)
            self._done()

    def delete_reference(self):
        case = self._selected_case()
        if case and self.app._choice('Удалить эталон', f'Удалить эталон {case}?',
                                     [('delete', 'Удалить'), ('cancel', 'Отмена')]) == 'delete':
            self.draft.delete_reference(case)
            self._done()

    def delete_word(self):
        sel = self.words_tab.selection()
        if sel:
            self.draft.delete_word(sel[0].split(':', 1)[1])
            self._done()

    def fix_finding(self, f):
        if f.kind == JAW_FIX:
            a, b = f.code.split(',')
            self.draft.swap(a, b)
            self._done(b)

    def _fix_selected(self):
        sel = self.lint_tab.selection()
        if sel:
            self.fix_finding(self.findings[int(sel[0].split('|')[0])])

    def _badge(self, it) -> str:
        """Значок колонки «Логика»: И · если · ≠ · ⚠ (сломанная ссылка)."""
        from .engine import effective_condition
        wb = self.draft.wb
        parts = []
        if it.children and it.combine == 'and':
            parts.append('И')
        cond = effective_condition(it, wb) if not it.children else None
        if cond:
            parts.append('⚠ если' if condition_refs(cond) - set(wb.by_id) else 'если')
        if any(it.id in p for p in wb.not_together):
            parts.append('≠')
        return ' '.join(parts)

    def _on_wheel(self, e):
        self.props_canvas.yview_scroll(-1 if e.delta > 0 else 1, 'units')

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

    def _forget_fields(self):
        """Поля справа — без записи (отмена, смена черновика): в них прежние значения."""
        self._props_code = None
        self._clear_props()

    def undo(self):
        self._forget_fields()
        self.draft.undo()
        self._done()

    def redo(self):
        self._forget_fields()
        self.draft.redo()
        self._done()

    def add_item(self):
        """Новая группа/пункт раздела — после выделенной группы (или в конец раздела)."""
        self._flush()
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
        self._flush()
        code = self.selected()
        if code is None or self._kind(code) == 'section':
            return
        it = self.draft.wb.by_id[code]
        group, after = (it.parent, code) if self._kind(code) == 'variant' else (code, None)
        new = self.draft.add(group, after, 'Новый вариант', 3)
        self._done(new)
        self._edit_text_soon()

    def move(self, delta: int):
        self._flush()
        code = self.selected()
        if code and self.draft.move(code, delta):
            self._done(code)

    def delete_selected(self, confirm: bool = True):
        self._flush()
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
            users = self.draft.referrers(code)
            if users:
                extra.append(f'на него ссылаются условия: {", ".join(users)}')
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
        # набранное в полях прежнего пункта — ему же, до того как поля пропадут
        # (щелчок по другому пункту меняет выделение раньше, чем уходит фокус)
        if self._commit_pending():
            self.refresh()
        self._clear_props()
        code = self.selected()
        self._props_code = code
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

            ttk.Label(p, text='Сочетание', font=app.f_small).pack(anchor='w', pady=(10, 0))
            self.combine_var = tk.StringVar(value=_COMBINE[it.combine])
            cb = ttk.Combobox(p, textvariable=self.combine_var, state='readonly',
                              values=list(_COMBINE.values()))
            cb.pack(fill='x')
            cb.bind('<<ComboboxSelected>>', lambda e: self._on_combine())

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
                ttk.Label(p, text='угадано', font=app.f_small,
                          foreground=MUTED).pack(anchor='w')
            self._condition_frame(p, it, key)
        if kind in ('single', 'variant'):
            self._pairs_frame(p, it)
        self.cond_rows = self.cond_rows if kind == 'single' else []
        self._xlsx_line(p, it)

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

        # самопроверка: где пункт выводится сейчас и где его ждут эталоны
        from .engine import build_protocol
        got = sum(code in {c for c, _ in build_protocol(wb, r.raw).lines} for r in wb.references)
        want = sum(any(c == code for c, _ in r.lines) for r in wb.references)
        self.refs_lbl = ttk.Label(p, text=f'по эталонам: выводится в {got}, ожидается в {want}',
                                  font=app.f_small, foreground=MUTED if got == want else WARN_TEXT)
        self.refs_lbl.pack(anchor='w', pady=(10, 0))

    def _edit_text_soon(self):
        self.top.after_idle(lambda: (self.text_box.focus_set(),
                                     self.text_box.tag_add('sel', '1.0', 'end-1c')))

    def text_field(self) -> str:
        return self.text_box.get('1.0', 'end-1c')

    def set_text_field(self, text: str):
        self.text_box.delete('1.0', 'end')
        self.text_box.insert('1.0', text)

    def _owner(self, widget: str) -> str | None:
        """Код пункта, чьи поля открыты, если поле ещё существует."""
        code = self._props_code
        w = getattr(self, widget, None)
        if code is None or code not in self.draft.wb.by_id or w is None or not w.winfo_exists():
            return None
        return code

    def _after_commit(self, old: str, new: str):
        """Выделение — у правленого пункта, если его не сменили щелчком."""
        sel = self.selected()
        self._done(new if sel in (None, old) else sel)

    def _commit_pending(self) -> bool:
        """Подтвердить набранное в полях (без перерисовки). True — что-то изменилось."""
        return any([self._on_words(refresh=False), self.commit_text(refresh=False),
                    self.commit_code(refresh=False)])

    def commit_text(self, refresh: bool = True) -> bool:
        code = self._owner('text_box')
        if code is None:
            return False
        text = _ws(self.text_field())
        if not text or text == _ws(self.draft.wb.by_id[code].text):
            return False
        self.draft.set_text(code, text)
        if refresh:
            self._after_commit(code, code)
        return True

    def set_code_field(self, code: str):
        self.code_entry.delete(0, 'end')
        self.code_entry.insert(0, code)

    def commit_code(self, refresh: bool = True) -> bool:
        code = self._owner('code_entry')
        if code is None:
            return False
        new = self.code_entry.get().strip().lower()
        if new == code:
            return False
        err = self.draft.set_code(code, new)
        if err and 'уже занят' in err and len(new) == len(code) and new[:-1] == code[:-1] \
                or err and 'уже занят' in err and len(code) > 2 and new[:2] == code[:2]:
            other = _ws(self.draft.wb.by_id[new].text)[:50]
            ans = self.app._choice('Код занят', f'Код «{new}» уже у «{other}».\n\n'
                                   f'Поменять коды местами?',
                                   [('swap', 'Поменять местами'), ('cancel', 'Отмена')])
            if ans != 'swap':
                return False
            self.draft.swap(code, new)
            err = None
        if err:
            if self.code_err.winfo_exists():
                self.code_err.configure(text=err)
            return False
        self._props_code = new
        if refresh:
            self._after_commit(code, new)
        return True

    def _renumber(self, code: str):
        self.draft.renumber(code)
        self._done(code)

    def _on_method(self):
        code = self._props_code
        key = next(k for k, v in METHOD_LABELS.items() if v == self.method_var.get())
        self.draft.set_prop(code, 'method', key)
        self._done(code)

    def _on_default(self):
        code = self._props_code
        self.draft.set_prop(code, 'default', self._variant_by_label.get(self.default_var.get()))
        self._done(code)

    # ---------- логика: условие, пары, сочетание ----------
    def _fields(self, own: str) -> dict[str, str]:
        """Подпись поля → код: группы и отдельные пункты по порядку протокола."""
        wb = self.draft.wb
        return {f'{it.id}  {_ws(it.text).rstrip(":")[:40]}': it.id for it in wb.items
                if it.level == 2 and it.id != own}

    def _values(self, field: str) -> dict[str, tuple[str, str | None]]:
        """Подпись значения → ('is', вариант) / ('mentioned', None)."""
        it = self.draft.wb.by_id.get(field)
        out = {}
        if it is not None and it.children:
            out = {f'= {t}': ('is', c) for c, t in _short_variants(it).items()}
        out[_MENTIONED] = ('mentioned', None)
        return out

    def _condition_frame(self, p, it, when: str):
        from .engine import effective_condition
        self.cond_rows: list[_CondRow] = []
        cond = effective_condition(it, self.draft.wb)
        need = when == 'condition'
        box = ttk.LabelFrame(p, text='Условие' if need else 'Условие (необязательно)', padding=8)
        box.pack(fill='x', pady=(10, 0))
        self.cond_note = ttk.Label(box, text='', font=self.app.f_small, foreground=MUTED,
                                   wraplength=340, justify='left')
        if cond is not None and not is_simple(cond):
            ttk.Label(box, text=format_condition(cond), wraplength=340).pack(anchor='w')
            self.cond_note.configure(text='Сложное условие — правится в xlsx (лист «Настройки»).')
            self.cond_note.pack(anchor='w', pady=(4, 0))
            return
        key = 'any' if cond and 'any' in cond else 'all'
        head = ttk.Frame(box)
        head.pack(fill='x')
        ttk.Label(head, text='Выводить, если верны' if need else '…и только если верны').pack(side='left')
        self.cond_join_var = tk.StringVar(value=_JOIN[key])
        cb = ttk.Combobox(head, textvariable=self.cond_join_var, state='readonly', width=13,
                          values=list(_JOIN.values()))
        cb.pack(side='left', padx=(6, 0))
        cb.bind('<<ComboboxSelected>>', lambda e: self.apply_condition())
        self._rows_box = ttk.Frame(box)
        self._rows_box.pack(fill='x', pady=(6, 0))
        self._field_codes = self._fields(it.id)
        for row in (cond or {}).get(key, []):
            self._add_row(row)
        ttk.Button(box, text='+ Строка', command=self.add_cond_row).pack(anchor='w', pady=(6, 0))
        first = next((r for r in (cond or {}).get(key, [])), None)
        if first:
            f = self.draft.wb.by_id.get(first['field'])
            what = f'«{_ws(f.text).rstrip(":")}»' if f else first['field']
            self.cond_note.configure(text=f'{what} не назван в записи — строка не выводится.')
        elif need:
            self.cond_note.configure(text='Условия нет — строка не выводится. Добавьте строку.')
        self.cond_note.pack(anchor='w', pady=(4, 0))
        if not it.condition and cond:
            ttk.Label(box, text='угадано по названию', font=self.app.f_small,
                      foreground=MUTED).pack(anchor='w')

    def _add_row(self, row: dict | None = None):
        i = len(self.cond_rows)
        fr = ttk.Frame(self._rows_box)
        fr.pack(fill='x', pady=1)
        not_var = tk.BooleanVar(value=bool(row and row.get('not')))
        ttk.Checkbutton(fr, text='НЕ', variable=not_var,
                        command=self.apply_condition).grid(row=0, column=0, sticky='w')
        field_var, value_var = tk.StringVar(), tk.StringVar()
        fcb = ttk.Combobox(fr, textvariable=field_var, state='readonly', width=18,
                           values=list(self._field_codes))
        fcb.grid(row=0, column=1, sticky='ew', padx=(4, 0))
        vcb = ttk.Combobox(fr, textvariable=value_var, state='readonly', width=16)
        vcb.grid(row=0, column=2, sticky='ew', padx=(4, 0))
        ttk.Button(fr, text='✕', width=3,
                   command=lambda: self.remove_cond_row(i)).grid(row=0, column=3, padx=(4, 0))
        fr.columnconfigure(1, weight=3)
        fr.columnconfigure(2, weight=2)
        r = _CondRow(not_var, field_var, value_var, vcb)
        self.cond_rows.append(r)
        if row:
            field = row['field']
            label = next((k for k, v in self._field_codes.items() if v == field), None)
            if label is None:                       # пункт удалён
                label = f'{field} — пункта нет'
                self._field_codes[label] = field
                ttk.Label(fr, text=f'⚠ Пункт {field} удалён. Выберите другой или уберите строку.',
                          foreground=WARN_TEXT, font=self.app.f_small).grid(
                              row=1, column=0, columnspan=4, sticky='w')
            field_var.set(label)
            values = self._values(field)
            vcb['values'] = list(values)
            want = ('mentioned', None) if row.get('mentioned') else ('is', row.get('is'))
            value_var.set(next((k for k, v in values.items() if v == want),
                               f'= {row.get("is")}' if 'is' in row else _MENTIONED))
        fcb.bind('<<ComboboxSelected>>', lambda e: self._on_cond_field(i))
        vcb.bind('<<ComboboxSelected>>', lambda e: self.apply_condition())

    def add_cond_row(self):
        if hasattr(self, '_rows_box') and self._rows_box.winfo_exists():
            self._add_row()

    def _on_cond_field(self, i: int):
        r = self.cond_rows[i]
        values = self._values(self._field_codes.get(r.field_var.get(), ''))
        r.value_cb['values'] = list(values)
        r.value_var.set(next(iter(values)))
        self.apply_condition()

    def remove_cond_row(self, i: int):
        self.cond_rows[i].field_var.set('')
        self.apply_condition(skip=i)

    def _condition_from_rows(self, skip: int | None = None) -> dict | None:
        rows = []
        for k, r in enumerate(self.cond_rows):
            field = self._field_codes.get(r.field_var.get())
            if k == skip or not field:
                continue
            kind, variant = self._values(field).get(r.value_var.get(), (None, None))
            if kind is None and r.value_var.get().startswith('= '):     # вариант удалён
                kind, variant = 'is', r.value_var.get()[2:]
            if kind is None:
                continue
            node = {'field': field, 'is': variant} if kind == 'is' else \
                {'field': field, 'mentioned': True}
            if r.not_var.get():
                node['not'] = True
            rows.append(node)
        if not rows:
            return None
        key = next(k for k, v in _JOIN.items() if v == self.cond_join_var.get())
        return {key: rows}

    def apply_condition(self, skip: int | None = None):
        code = self._props_code
        if code is None:
            return
        node = self._condition_from_rows(skip)
        if node != self.draft.wb.by_id[code].condition:
            self.draft.set_condition(code, node)
        self._done(code)

    @property
    def pairs_list(self) -> list[str]:
        code = self._props_code
        return [b if a == code else a for a, b in self.draft.wb.not_together if code in (a, b)]

    def _pairs_frame(self, p, it):
        wb = self.draft.wb
        box = ttk.LabelFrame(p, text='Не вместе с', padding=8)
        box.pack(fill='x', pady=(10, 0))
        for other in self.pairs_list:
            row = ttk.Frame(box)
            row.pack(fill='x', pady=1)
            text = _ws(wb.by_id[other].text)[:40] if other in wb.by_id else 'пункта нет'
            ttk.Label(row, text=f'{other}  {text}').pack(side='left')
            ttk.Button(row, text='Перейти', command=lambda o=other: self.select(o)).pack(side='right')
            ttk.Button(row, text='✕', width=3,
                       command=lambda o=other: self.remove_pair(o)).pack(side='right', padx=(0, 4))
        choices = {f'{x.id}  {_ws(x.text)[:40]}': x.id for x in wb.items
                   if x.level >= 2 and not x.children and x.id != it.id
                   and x.id not in self.pairs_list}
        add = ttk.Frame(box)
        add.pack(fill='x', pady=(4, 0))
        ttk.Label(add, text='+ не вместе с').pack(side='left')
        var = tk.StringVar()
        cb = ttk.Combobox(add, textvariable=var, state='readonly', values=list(choices))
        cb.pack(side='left', fill='x', expand=True, padx=(6, 0))
        cb.bind('<<ComboboxSelected>>', lambda e: self.add_pair(choices[var.get()]))
        ttk.Label(box, text='Если в записи оба — в протоколе будут оба с пометкой «проверьте».',
                  font=self.app.f_small, foreground=MUTED, wraplength=340,
                  justify='left').pack(anchor='w', pady=(4, 0))

    def add_pair(self, other: str):
        code = self._props_code
        self.draft.add_pair(code, other)
        self._done(code)

    def remove_pair(self, other: str):
        code = self._props_code
        self.draft.remove_pair(code, other)
        self._done(code)

    def _xlsx_line(self, p, it):
        from .engine import effective_condition
        parts = []
        if it.children and it.combine == 'and':
            parts.append('Сочетание И')
        cond = effective_condition(it, self.draft.wb) if not it.children else None
        if cond:
            parts.append(f'Условие {format_condition(cond)}')
        if self.pairs_list:
            parts.append(f'Не вместе с {", ".join(self.pairs_list)}')
        self.xlsx_lbl = ttk.Label(p, text=('В xlsx, лист «Настройки»: ' + ' · '.join(parts))
                                  if parts else '', font=self.app.f_small, foreground=MUTED,
                                  wraplength=360, justify='left')
        self.xlsx_lbl.pack(anchor='w', pady=(6, 0))

    def _on_combine(self):
        code = self._props_code
        value = next(k for k, v in _COMBINE.items() if v == self.combine_var.get())
        self.draft.set_combine(code, value)
        self._done(code)

    def _on_when(self):
        code = self._props_code
        key = next(k for k, v in WHEN_LABELS.items() if v == self.when_var.get())
        self.draft.set_prop(code, 'when', key)
        self._done(code)

    def _on_words(self, refresh: bool = True) -> bool:
        code = self._owner('words_entry')
        if code is None:
            return False
        words = [w.strip() for w in self.words_entry.get().split(',') if w.strip()]
        if words == self.draft.wb.by_id[code].words:
            return False
        self.draft.set_prop(code, 'words', words)
        if refresh:
            self._after_commit(code, code)
        return True

    # ---------- сохранение, закрытие, xlsx ----------
    def _flush(self):
        if self._commit_pending():
            self._done()

    def save(self) -> bool:
        self._flush()
        if not self.draft.changed:
            return True
        broken = [r for r in self.results if not r.ok]
        if broken and self.app._choice(
                'Сохранить пресет',
                f'Сломано эталонов: {len(broken)} из {len(self.results)} '
                f'(см. вкладку «Эталоны»).\n\nСохранить всё равно?',
                [('save', 'Сохранить'), ('cancel', 'Отмена')]) != 'save':
            return False
        status = self.ctl.save_draft()
        self.app.after_preset_saved(self.draft.preset_id, status)
        self._done()
        return True

    def discard(self):
        if self.draft.changed and self.app._choice(
                'Отменить изменения', f'Отменить все несохранённые правки ({self.draft.changed})?',
                [('discard', 'Отменить правки'), ('cancel', 'Оставить')]) != 'discard':
            return
        self._drop_draft()
        self._done()

    def _drop_draft(self):
        self._forget_fields()
        pid = self.draft.preset_id
        self.ctl.draft = None
        self.draft = self.ctl.open_draft(pid)

    def close(self):
        self._flush()
        if self.draft.changed:
            ans = self.app._choice('Закрыть редактор',
                                   f'Есть несохранённые правки: {self.draft.changed}.',
                                   [('save', 'Сохранить'), ('discard', 'Не сохранять'),
                                    ('cancel', 'Отмена')])
            if ans == 'save':
                if not self.save():
                    return
            elif ans == 'discard':
                self.ctl.draft = None
            else:
                return
        self.top.destroy()

    def import_xlsx(self):
        p = filedialog.askopenfilename(parent=self.top, title='Импорт пресета из xlsx',
                                       filetypes=[('Excel', '*.xlsx'), ('Все файлы', '*.*')])
        if p:
            self.import_path(Path(p))

    def import_path(self, path: Path):
        """Файл целиком заменяет черновик — одной отменяемой правкой."""
        from .workbook import WorkbookError, load_workbook_file
        try:
            wb = load_workbook_file(path)
        except WorkbookError as e:
            self.status_lbl.configure(text=f'✗ {e}', foreground=WARN_TEXT)
            return
        if wb.problems:
            self.status_lbl.configure(text=f'✗ ошибки в файле: {"; ".join(wb.problems[:3])}',
                                      foreground=WARN_TEXT)
            return
        self.draft.import_wb(wb)
        self._done()

    def export_xlsx(self):
        from datetime import date
        if self.draft.changed and not self._save_first():
            return
        p = filedialog.asksaveasfilename(parent=self.top, title='Экспорт пресета в xlsx',
                                         defaultextension='.xlsx',
                                         initialfile=f'{self.draft.wb.name}-{date.today():%Y-%m-%d}.xlsx',
                                         filetypes=[('Excel', '*.xlsx')])
        if p:
            self.export_path(Path(p))

    def _save_first(self) -> bool:
        return self.app._choice('Экспорт xlsx', 'Сначала сохранить правки? Выгружается '
                                'сохранённый пресет.',
                                [('save', 'Сохранить и выгрузить'), ('cancel', 'Отмена')]) == 'save' \
            and self.save()

    def export_path(self, path: Path):
        self._flush()
        if self.draft.changed and not self._save_first():
            return
        msg = self.ctl.export_xlsx(path, preset_id=self.draft.preset_id)
        self.status_lbl.configure(text=msg, foreground=MUTED)
        self.app._refresh_presets()

    def _on_ctrl(self, e):
        """Ctrl+Z / Ctrl+Y — по физической клавише (и в русской раскладке);
        в полях ввода — их собственная правка."""
        if isinstance(e.widget, (tk.Text, tk.Entry, ttk.Entry)):
            return None
        key = {52: 'z', 29: 'y', 90: 'z', 89: 'y'}.get(e.keycode)
        if key == 'z':
            self.undo()
            return 'break'
        if key == 'y':
            self.redo()
            return 'break'
        return None
