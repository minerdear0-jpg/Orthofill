import sys; sys.path.insert(0, '/tmp/claude-1000/-home-sysadm-Sync-Projects-Orthofill/3b27c05f-9b19-4351-8168-aef7e8d7baa4/scratchpad/critic')
from base import *

def props(p, root, narrow, broken=False):
    head(p, root, 'Отдельный пункт', '4h1', 'Контроль положения дуги, окклюзионных контактов, фиксации лигатур.')
    ttk.Label(p, text='Когда в протоколе', font=root.f_small).pack(anchor='w', pady=(8, 0))
    cb = ttk.Combobox(p, state='readonly', values=['всегда', 'если упомянут', 'если выполнено условие'])
    cb.set('если выполнено условие'); cb.pack(fill='x')

    lf = ttk.LabelFrame(p, text='Условие', padding=(8, 4, 8, 6)); lf.pack(fill='x', pady=(8, 0))
    j = ttk.Frame(lf); j.pack(fill='x')
    ttk.Label(j, text='Выполнено, если верны').pack(side='left')
    jc = ttk.Combobox(j, state='readonly', width=11, values=['все строки', 'любая строка']); jc.set('все строки')
    jc.pack(side='left', padx=6)
    g = ttk.Frame(lf); g.pack(fill='x', pady=(4, 0))
    g.columnconfigure(1, weight=3); g.columnconfigure(2, weight=2)
    rows = [(False, '2b  Тип системы', '= лигатурная', None)]
    if broken:
        rows.append((True, '4p  — пункта нет', 'упомянут', 'Пункт 4p удалён. Выберите другой или уберите строку.'))
    r = 0
    for neg, f, v, err in rows:
        c = ttk.Checkbutton(g, text='НЕ'); c.grid(row=r, column=0, sticky='w')
        if neg: c.state(['selected', '!alternate'])
        else: c.state(['!selected', '!alternate'])
        fc = ttk.Combobox(g, state='readonly', values=[f]); fc.set(f); fc.grid(row=r, column=1, sticky='ew', padx=4, pady=2)
        vc = ttk.Combobox(g, state='readonly', values=[v]); vc.set(v); vc.grid(row=r, column=2, sticky='ew', pady=2)
        ttk.Button(g, text='✕', width=2).grid(row=r, column=3, padx=(4, 0))
        if err:
            r += 1
            ttk.Label(g, text='⚠ ' + err, foreground=WARN, font=root.f_small).grid(row=r, column=1, columnspan=3, sticky='w')
        r += 1
    b = ttk.Frame(lf); b.pack(fill='x', pady=(4, 0))
    ttk.Button(b, text='+ Строка').pack(side='left')
    ttk.Label(lf, text='Поля нет в записи — строка не выводится.', font=root.f_small,
              foreground=MUTED).pack(anchor='w', pady=(4, 0))

    lf2 = ttk.LabelFrame(p, text='Не вместе с', padding=(8, 4, 8, 6)); lf2.pack(fill='x', pady=(8, 0))
    nr = ttk.Frame(lf2); nr.pack(fill='x')
    ttk.Label(nr, text='4h2  Контроль … закрытия клипс.').pack(side='left')
    ttk.Button(nr, text='✕', width=2).pack(side='right')
    ttk.Button(lf2, text='+ Добавить…').pack(anchor='w', pady=(4, 0))
    ttk.Label(lf2, text='Оба в записи — выводятся оба с пометкой «проверьте».', font=root.f_small,
              foreground=MUTED, wraplength=480 if narrow else 360).pack(anchor='w', pady=(4, 0))

    ttk.Label(p, text='В xlsx:  2b = 2b2' + ('  И НЕ 4p' if broken else '') + '   ·   не вместе с 4h2',
              font=root.f_small, foreground=MUTED).pack(anchor='w', pady=(8, 0))

which = sys.argv[1]
if which == 'wide': window(props, 'A-wide.png', 1040, 680)
if which == 'narrow': window(props, 'A-narrow.png', 560, 760, narrow=True)
if which == 'broken': window(lambda p, r, n: props(p, r, n, True), 'A-broken.png', 1040, 720, broken={'4h1'},
                              counter='эталоны 2/2 · находок 2')
