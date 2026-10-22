import sys; sys.path.insert(0, '/tmp/claude-1000/-home-sysadm-Sync-Projects-Orthofill/3b27c05f-9b19-4351-8168-aef7e8d7baa4/scratchpad/critic')
import base
from base import *

_orig_tree = base.tree
def tree2(parent, root, sel='4h1', broken=None, height=14):
    fr = _orig_tree(parent, root, sel, broken, height)
    s = fr.winfo_children()[0]
    c = ttk.Checkbutton(s, text='только с логикой'); c.state(['!alternate', '!selected']); c.pack(side='left', padx=(8, 0))
    tv = fr.winfo_children()[1]
    tv.column('#0', width=340); tv.column('logic', width=58)
    return fr
base.tree = tree2

def props(outer, root, narrow, scroll=0.0):
    cv = tk.Canvas(outer, highlightthickness=0, borderwidth=0, background='#fafafa')
    sb = ttk.Scrollbar(outer, orient='vertical', command=cv.yview)
    p = ttk.Frame(cv)
    win = cv.create_window(0, 0, window=p, anchor='nw')
    cv.configure(yscrollcommand=sb.set)
    sb.pack(side='right', fill='y'); cv.pack(side='left', fill='both', expand=True)
    p.bind('<Configure>', lambda e: cv.configure(scrollregion=cv.bbox('all')))
    cv.bind('<Configure>', lambda e: cv.itemconfigure(win, width=e.width - 4))
    head(p, root, 'Отдельный пункт', '4h1', 'Контроль положения дуги, окклюзионных контактов, фиксации лигатур.')
    ttk.Label(p, text='Когда в протоколе', font=root.f_small).pack(anchor='w', pady=(8, 0))
    cb = ttk.Combobox(p, state='readonly', values=['всегда', 'если упомянут', 'по условию']); cb.set('по условию'); cb.pack(fill='x')
    lf = ttk.LabelFrame(p, text='Условие', padding=(8, 4, 8, 6)); lf.pack(fill='x', pady=(8, 0))
    j = ttk.Frame(lf); j.pack(fill='x')
    ttk.Label(j, text='Выводить, если верны').pack(side='left')
    jc = ttk.Combobox(j, state='readonly', width=11, values=['все строки', 'любая строка']); jc.set('все строки'); jc.pack(side='left', padx=6)
    g = ttk.Frame(lf); g.pack(fill='x', pady=(4, 0)); g.columnconfigure(1, weight=3); g.columnconfigure(2, weight=2)
    for r, (neg, f, v) in enumerate([(False, '2b  Тип системы', '= вестибулярная лигатурная')]):
        c = ttk.Checkbutton(g, text='НЕ'); c.state(['!alternate', 'selected' if neg else '!selected']); c.grid(row=r, column=0)
        fc = ttk.Combobox(g, state='readonly'); fc.set(f); fc.grid(row=r, column=1, sticky='ew', padx=4, pady=2)
        vc = ttk.Combobox(g, state='readonly'); vc.set(v); vc.grid(row=r, column=2, sticky='ew', pady=2)
        ttk.Button(g, text='✕', width=2).grid(row=r, column=3, padx=(4, 0))
    b = ttk.Frame(lf); b.pack(fill='x', pady=(4, 0))
    ttk.Button(b, text='+ Строка').pack(side='left')
    ttk.Label(lf, text='Тип системы не назван в записи — строка не выводится.', font=root.f_small,
              foreground=MUTED, wraplength=460 if narrow else 380).pack(anchor='w', pady=(4, 0))
    lf2 = ttk.LabelFrame(p, text='Не вместе с', padding=(8, 4, 8, 6)); lf2.pack(fill='x', pady=(8, 0))
    nr = ttk.Frame(lf2); nr.pack(fill='x')
    ttk.Label(nr, text='4h2  Контроль … закрытия клипс.').pack(side='left')
    ttk.Button(nr, text='Перейти').pack(side='right', padx=(4, 0))
    ttk.Button(nr, text='✕', width=2).pack(side='right')
    ttk.Button(lf2, text='+ Добавить пункт…').pack(anchor='w', pady=(4, 0))
    ttk.Label(lf2, text='Если в записи оба — в протоколе будут оба с пометкой «проверьте».', font=root.f_small,
              foreground=MUTED, wraplength=460 if narrow else 380).pack(anchor='w', pady=(4, 0))
    ttk.Label(p, text='В xlsx, лист «Настройки»:  Условие  2b = 2b2   ·   Не вместе с  4h2',
              font=root.f_small, foreground=MUTED).pack(anchor='w', pady=(8, 0))
    ttk.Label(p, text='Так будет в протоколе', font=root.f_small).pack(anchor='w', pady=(10, 0))
    ttk.Label(p, text='Контроль положения дуги, окклюзионных контактов, фиксации лигатур.', foreground=ACCENT,
              wraplength=460 if narrow else 380, justify='left').pack(anchor='w')
    ttk.Label(p, text='есть в эталонах: 1 из 2', font=root.f_small, foreground=MUTED).pack(anchor='w', pady=(10, 0))
    if scroll:
        root.after(300, lambda: (cv.update_idletasks(), cv.configure(scrollregion=cv.bbox('all')), cv.yview_moveto(scroll)))

which = sys.argv[1]
if which == 'wide': window(props, 'R-wide.png', 1040, 680)
if which == 'narrow': window(lambda p, r, n: props(p, r, n, 0.42), 'R-narrow.png', 560, 760, narrow=True)
