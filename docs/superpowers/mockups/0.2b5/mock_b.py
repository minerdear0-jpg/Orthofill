import sys; sys.path.insert(0, '/tmp/claude-1000/-home-sysadm-Sync-Projects-Orthofill/3b27c05f-9b19-4351-8168-aef7e8d7baa4/scratchpad/critic')
from base import *

def cb(parent, val, vals, w):
    c = ttk.Combobox(parent, state='readonly', values=vals, width=w); c.set(val); c.pack(side='left', padx=2); return c

def props(p, root, narrow):
    head(p, root, 'Отдельный пункт', '4h1', 'Контроль положения дуги, окклюзионных контактов, фиксации лигатур.')
    ttk.Label(p, text='Когда в протоколе', font=root.f_small).pack(anchor='w', pady=(10, 2))
    l1 = ttk.Frame(p); l1.pack(fill='x', pady=2)
    ttk.Label(l1, text='Выводить').pack(side='left')
    cb(l1, 'если', ['всегда', 'если упомянут', 'если'], 12)
    l2 = ttk.Frame(p); l2.pack(fill='x', pady=2)
    ttk.Label(l2, text='      ').pack(side='left')
    cb(l2, 'Тип системы', ['Тип системы'], 13)
    cb(l2, '—', ['—', 'не'], 3)
    cb(l2, 'лигатурная', ['лигатурная', 'самолигируемая', 'упомянут'], 12)
    ttk.Button(l2, text='✕', width=2).pack(side='left', padx=2)
    l3 = ttk.Frame(p); l3.pack(fill='x', pady=2)
    cb(l3, 'и', ['и', 'или'], 3)
    cb(l3, 'Эластическая цепочка без шага', ['…'], 13)
    cb(l3, 'не', ['—', 'не'], 3)
    cb(l3, 'упомянута', ['упомянута'], 12)
    ttk.Button(l3, text='✕', width=2).pack(side='left', padx=2)
    ttk.Button(p, text='+ ещё условие').pack(anchor='w', pady=(4, 0))

    ttk.Label(p, text='Читается так:', font=root.f_small, foreground=MUTED).pack(anchor='w', pady=(10, 0))
    ttk.Label(p, text='«Выводить, если тип системы — лигатурная и эластическая цепочка без шага не упомянута»',
              foreground=ACCENT, wraplength=480 if narrow else 380, justify='left').pack(anchor='w')

    ttk.Label(p, text='Никогда вместе с', font=root.f_small).pack(anchor='w', pady=(10, 2))
    l4 = ttk.Frame(p); l4.pack(fill='x')
    cb(l4, 'Контроль … закрытия клипс.', ['…'], 30)
    ttk.Button(l4, text='✕', width=2).pack(side='left', padx=2)
    ttk.Button(p, text='+ ещё пункт').pack(anchor='w', pady=(4, 0))

which = sys.argv[1]
if which == 'wide': window(props, 'B-wide.png', 1040, 680)
if which == 'narrow': window(props, 'B-narrow.png', 560, 760, narrow=True)
