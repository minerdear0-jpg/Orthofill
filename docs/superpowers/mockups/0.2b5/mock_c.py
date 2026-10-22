import sys; sys.path.insert(0, '/tmp/claude-1000/-home-sysadm-Sync-Projects-Orthofill/3b27c05f-9b19-4351-8168-aef7e8d7baa4/scratchpad/critic')
from base import *

RULES = [  # code, item, combine, when, cond, notwith
    ('2b', 'Тип системы', 'ИЛИ', '', '', ''),
    ('4d', 'Смена одиночных эластических лигатур', 'ИЛИ', 'если упомянут', 'НЕ 2b = 2b1', ''),
    ('4f', 'Назначены межчелюстные эластики', 'И', '', '', ''),
    ('4g', 'Юстировка дуги', 'И', '', '', ''),
    ('4h1', 'Контроль … фиксации лигатур.', '', 'если условие', '2b = 2b2', '4h2'),
    ('4h2', 'Контроль … закрытия клипс.', '', 'если условие', '2b = 2b1', '4h1'),
]

def page(p, root, narrow):
    top = ttk.Frame(p); top.pack(fill='x', pady=(0, 6))
    ttk.Label(top, text='Найти:').pack(side='left'); ttk.Entry(top).pack(side='left', fill='x', expand=True, padx=6)
    ttk.Checkbutton(top, text='только с логикой').pack(side='left')
    cols = ('code', 'item', 'comb', 'when', 'cond', 'nw')
    tv = ttk.Treeview(p, columns=cols, show='headings', height=7 if narrow else 9)
    for c, t, w in zip(cols, ('Код', 'Пункт', 'Сочетание', 'Когда', 'Условие', 'Не вместе с'),
                       (48, 250, 80, 110, 120, 90)):
        tv.heading(c, text=t, anchor='w'); tv.column(c, width=w if not narrow else max(40, w * 52 // 100), anchor='w',
                                                      stretch=(c == 'item'))
    for r in RULES:
        tv.insert('', 'end', iid=r[0], values=r)
    tv.selection_set('4h1')
    tv.pack(fill='both', expand=True)
    ed = ttk.LabelFrame(p, text='4h1  Контроль положения дуги, окклюзионных контактов, фиксации лигатур.', padding=8)
    ed.pack(fill='x', pady=(8, 0))
    ed.columnconfigure(1, weight=1)
    ttk.Label(ed, text='Когда в протоколе').grid(row=0, column=0, sticky='w')
    c = ttk.Combobox(ed, state='readonly', values=['всегда', 'если упомянут', 'если условие']); c.set('если условие')
    c.grid(row=0, column=1, sticky='ew', pady=2)
    ttk.Label(ed, text='Условие').grid(row=1, column=0, sticky='w')
    e = ttk.Entry(ed); e.insert(0, '2b = 2b2'); e.grid(row=1, column=1, sticky='ew', pady=2)
    ttk.Button(ed, text='Вставить из дерева…').grid(row=1, column=2, padx=(6, 0))
    ttk.Label(ed, text='= Тип системы: вестибулярная лигатурная.', foreground=ACCENT, font=root.f_small).grid(
        row=2, column=1, sticky='w')
    ttk.Label(ed, text='Не вместе с').grid(row=3, column=0, sticky='w', pady=(6, 0))
    e2 = ttk.Entry(ed); e2.insert(0, '4h2'); e2.grid(row=3, column=1, sticky='ew', pady=(6, 2))
    ttk.Label(ed, text='= Контроль положения дуги, окклюзионных контактов, закрытия клипс.', foreground=ACCENT,
              font=root.f_small, wraplength=420 if narrow else 700).grid(row=4, column=1, sticky='w')
    ttk.Label(ed, text='Пишется как в листе «Настройки»: 2b = 2b2 И НЕ 4p; НЕ, И, ИЛИ, скобки; «4p упомянут».',
              foreground=MUTED, font=root.f_small, wraplength=480 if narrow else 800).grid(
        row=5, column=0, columnspan=3, sticky='w', pady=(6, 0))
page.whole_page = True; page.tab = 'Логика (6)'

which = sys.argv[1]
if which == 'wide': window(page, 'C-wide.png', 1040, 680)
if which == 'narrow': window(page, 'C-narrow.png', 560, 760, narrow=True)
