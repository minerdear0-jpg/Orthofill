import sys, subprocess, tkinter as tk
from tkinter import ttk, font as tkfont
import sv_ttk

OUT = '/tmp/claude-1000/-home-sysadm-Sync-Projects-Orthofill/3b27c05f-9b19-4351-8168-aef7e8d7baa4/scratchpad/critic/'
MUTED, WARN, ACCENT = '#5f6b7a', '#b34700', '#005fb8'

TREE = [  # (iid, parent, text, code, logic, open)
    ('2', '', 'Анамнез: активация', '2', '', True),
    ('2a', '2', 'Находится на этапе активного ортодонтического лечения.', '2a', '', False),
    ('2b', '2', 'Тип системы  (2)', '2b', '', False),
    ('2c', '2', 'Этап  (3)', '2c', '', False),
    ('4', '', 'Лечение:', '4', '', True),
    ('4c', '4', 'Смена дуги на нижней челюсти  (21)', '4c', '', False),
    ('4d', '4', 'Смена одиночных эластических лигатур  (3)', '4d', 'если', False),
    ('4e', '4', 'Подвязывание зубов металлической длинной лигатурой  (2)', '4e', '', False),
    ('4p', '4', 'Эластическая цепочка без шага  (2)', '4p', '', False),
    ('4f', '4', 'Назначены межчелюстные эластики  (6)', '4f', 'И', False),
    ('4g', '4', 'Юстировка дуги  (3)', '4g', 'И', False),
    ('4h1', '4', 'Контроль положения дуги, окклюзионных контактов, фиксации лигатур.', '4h1', 'если ≠', False),
    ('4h2', '4', 'Контроль положения дуги, окклюзионных контактов, закрытия клипс.', '4h2', 'если ≠', False),
    ('4j', '4', 'Выполнен фотопротокол (внутриротовые снимки этапа)', '4j', '', False),
    ('4k', '4', 'Динамика лечения  (2)', '4k', '', False),
]

def setup(title_extra=''):
    root = tk.Tk()
    sv_ttk.set_theme('light')
    fams = tkfont.families()
    fam = 'Segoe UI' if 'Segoe UI' in fams else tkfont.nametofont('TkDefaultFont').actual('family')
    for n in ('TkDefaultFont', 'TkTextFont', 'TkHeadingFont', 'TkMenuFont'):
        tkfont.nametofont(n).configure(family=fam, size=10)
    root.f_small = (fam, 9)
    root.f_label = (fam, 9, 'bold')
    root.f_head = (fam, 13, 'bold')
    root.fam = fam
    root.title('Orthofill 0.2 beta 5 — пресет «order-new-aktiv»' + title_extra)
    return root

def tree(parent, root, sel='4h1', broken=None, height=14):
    fr = ttk.Frame(parent)
    s = ttk.Frame(fr); s.pack(fill='x', pady=(0, 6))
    ttk.Label(s, text='Найти:').pack(side='left')
    ttk.Entry(s).pack(side='left', fill='x', expand=True, padx=(6, 0))
    tv = ttk.Treeview(fr, columns=('code', 'logic'), height=height)
    tv.heading('#0', text='Пункт'); tv.heading('code', text='Код'); tv.heading('logic', text='Логика')
    tv.column('#0', width=300, minwidth=160, stretch=True); tv.column('code', width=52, stretch=False, anchor='w')
    tv.column('logic', width=64, stretch=False, anchor='w')
    tv.tag_configure('warn', foreground=WARN)
    for iid, p, text, code, logic, op in TREE:
        tags = ()
        if broken and iid in broken:
            logic = '⚠ ' + logic; tags = ('warn',)
        tv.insert(p, 'end', iid=iid, text=text, values=(code, logic), open=op, tags=tags)
    if sel:
        tv.selection_set(sel); tv.see(sel)
    tv.pack(fill='both', expand=True)
    b = ttk.Frame(fr); b.pack(fill='x', pady=(6, 0))
    for t in ('+ Пункт', '+ Вариант', '↑', '↓', 'Удалить'):
        ttk.Button(b, text=t).pack(side='left', padx=(0, 6))
    return fr

def window(build_props, out, w, h, narrow=False, sel='4h1', broken=None, tabs_extra=None, counter='эталоны 2/2 · находок 1'):
    root = setup()
    root.geometry(f'{w}x{h}+40+40')
    top = ttk.Frame(root, padding=(12, 8, 12, 8)); top.pack(fill='both', expand=True)
    hd = ttk.Frame(top); hd.pack(fill='x')
    ttk.Label(hd, text='order-new-aktiv', font=root.f_head).pack(side='left')
    ttk.Button(hd, text='Экспорт xlsx…').pack(side='right')
    ttk.Button(hd, text='Импорт xlsx…').pack(side='right', padx=6)
    bot = ttk.Frame(top); bot.pack(side='bottom', fill='x', pady=(8, 0))
    ttk.Button(bot, text='↶ Отменить').pack(side='left')
    if not narrow:
        ttk.Button(bot, text='↷ Вернуть').pack(side='left', padx=6)
    ttk.Label(bot, text='● Изменено: 2', foreground=WARN).pack(side='left', padx=8)
    ttk.Label(bot, text=counter, foreground=WARN if 'находок 0' not in counter else MUTED).pack(side='left')
    ttk.Button(bot, text='Сохранить', style='Accent.TButton').pack(side='right')
    if not narrow:
        ttk.Button(bot, text='Отменить изменения').pack(side='right', padx=6)
    nb = ttk.Notebook(top); nb.pack(fill='both', expand=True, pady=(8, 0))
    page = ttk.Frame(nb, padding=8)
    whole = getattr(build_props, 'whole_page', False)
    if whole:
        nb.add(ttk.Frame(nb), text='Пункты протокола'); nb.add(page, text=build_props.tab)
    else:
        nb.add(page, text='Пункты протокола')
    for t in (tabs_extra or []):
        nb.add(ttk.Frame(nb), text=t)
    nb.add(ttk.Frame(nb), text='Эталоны (2)'); nb.add(ttk.Frame(nb), text='Слова врача (0)')
    nb.add(ttk.Frame(nb), text='Проверка (1)')
    if whole:
        nb.select(page); build_props(page, root, narrow)
    elif narrow:
        tree(page, root, sel, broken, height=6).pack(fill='x')
        ttk.Separator(page).pack(fill='x', pady=8)
        pr = ttk.Frame(page); pr.pack(fill='both', expand=True)
        build_props(pr, root, narrow)
    else:
        pw = ttk.PanedWindow(page, orient='horizontal'); pw.pack(fill='both', expand=True)
        pw.add(tree(pw, root, sel, broken), weight=3)
        pr = ttk.Frame(pw, padding=(12, 0, 0, 0)); pw.add(pr, weight=2)
        build_props(pr, root, narrow)
    def shot():
        root.update()
        subprocess.run(['import', '-window', root.wm_frame(), OUT + out])
        root.destroy()
    root.after(900, shot)
    root.mainloop()

def head(p, root, kind, code, text):
    ttk.Label(p, text=kind, font=root.f_label, foreground=MUTED).pack(anchor='w')
    r = ttk.Frame(p); r.pack(fill='x', pady=(2, 0))
    ttk.Label(r, text='Код:').pack(side='left')
    e = ttk.Entry(r, width=6); e.insert(0, code); e.pack(side='left', padx=(6, 0))
    ttk.Label(p, text='Текст в протоколе', font=root.f_small).pack(anchor='w', pady=(6, 0))
    t = tk.Text(p, height=2, wrap='word', relief='solid', borderwidth=1, highlightthickness=0,
                padx=6, pady=3, font=(root.fam, 10))
    t.insert('1.0', text); t.pack(fill='x')
