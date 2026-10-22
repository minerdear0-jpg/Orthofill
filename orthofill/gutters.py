"""0.5 beta 7: колонки слева от записи и от протокола (режим «Оболочка»).

Слева от записи — номер готовой строки-пути в цветном кружке; слева от протокола —
тот же номер и цвет у строки, которая из неё, и «откуда» у остальных. Щелчок по
строке колонки протокола — курсор на её строку записи. Колонки — холсты рядом с
полями: текст протокола не меняется (копирование и холст 0.5 b3 не задеты)."""
from __future__ import annotations

import tkinter as tk

from .links import chip_color, note_lines, row_sources

IN_W, OUT_W, R = 28, 84, 9       # ширина колонок, радиус кружка (px)
_MUTED, _RING = '#8a8a83', '#1b1b1a'


class Gutters:
    def __init__(self, app):
        self.app = app
        self.in_gutter = self._canvas(app.raw_txt, IN_W)
        self.out_gutter = self._canvas(app.out_txt, OUT_W)
        self._note: dict[int, str] = {}
        self._sources: list[tuple[list[int], str]] = []
        self._job = None
        self.shown = False
        for txt in (app.raw_txt, app.out_txt):
            self._follow_scroll(txt)
            txt.bind('<Configure>', lambda e: self.draw(), add='+')
        app.raw_txt.bind('<KeyRelease>', lambda e: self.schedule(), add='+')
        app.raw_txt.bind('<ButtonRelease-1>', lambda e: self.draw(), add='+')
        self.out_gutter.bind('<Button-1>', self._click_out)
        self.in_gutter.bind('<Button-1>', self._click_in)

    def _canvas(self, txt: tk.Text, width: int) -> tk.Canvas:
        return tk.Canvas(txt.master, width=width, bg=txt.cget('background'),
                         highlightthickness=0, borderwidth=0, cursor='hand2')

    def _follow_scroll(self, txt: tk.Text):
        orig = txt.cget('yscrollcommand')

        def scrolled(first, last):
            if orig:
                txt.tk.eval(f'{orig} {first} {last}')
            self.draw()
        txt.configure(yscrollcommand=scrolled)

    # ---------- видимость ----------
    def show(self, on: bool):
        if on == self.shown:
            return
        self.shown = on
        for c, txt in ((self.in_gutter, self.app.raw_txt), (self.out_gutter, self.app.out_txt)):
            if on:
                c.pack(side='left', fill='y', before=txt)
            else:
                c.pack_forget()
                c.delete('all')
        if on:
            self.refresh()

    # ---------- пересчёт ----------
    def schedule(self):
        """После набора — не чаще раза в 100 мс."""
        if not self.shown or self._job is not None:
            return
        self._job = self.app.root.after(100, self._run)

    def _run(self):
        self._job = None
        self.refresh()

    def refresh(self):
        app = self.app
        wb = app.ctl.workbook
        if not self.shown or wb is None:
            return
        self._note = note_lines(wb, app.raw_txt.get('1.0', 'end-1c'))
        lines = app._canvas_lines if app._canvas_active else []
        self._sources = row_sources(wb, lines, self._note) if lines else []
        self.draw()

    # ---------- рисование ----------
    def draw(self):
        if not self.shown:
            return
        app = self.app
        cur = int(app.raw_txt.index('insert').split('.')[0])
        c = self.in_gutter
        c.delete('all')
        for n in self._note:
            y = _middle(app.raw_txt, n)
            if y is not None:
                self._chip(c, IN_W // 2, y, n, n == cur)
        c = self.out_gutter
        c.delete('all')
        for i, (nums, src) in enumerate(self._sources, 1):
            y = _middle(app.out_txt, i)
            if y is None:
                continue
            if nums:
                for k, n in enumerate(nums[:3]):
                    self._chip(c, R + 4 + k * (2 * R + 2), y, n, n == cur)
            elif src:
                c.create_text(OUT_W - 6, y, text=src, anchor='e', fill=_MUTED,
                              font=app.f_small, tags=('src',))

    def _chip(self, c: tk.Canvas, x: int, y: float, n: int, current: bool):
        c.create_oval(x - R, y - R, x + R, y + R, fill=chip_color(n),
                      outline=_RING if current else '', width=2 if current else 0,
                      tags=('chip', f'n{n}'))
        c.create_text(x, y, text=str(n), fill='#ffffff', font=self.app.f_label,
                      tags=('num', f'n{n}'))

    # ---------- щелчок ----------
    def _click_out(self, e):
        i = int(self.app.out_txt.index(f'@0,{e.y}').split('.')[0])
        if 1 <= i <= len(self._sources) and self._sources[i - 1][0]:
            self.jump(self._sources[i - 1][0][0])

    def _click_in(self, e):
        self.jump(int(self.app.raw_txt.index(f'@0,{e.y}').split('.')[0]))

    def jump(self, n: int):
        """Курсор — в конец строки записи n; её место в протоколе подсвечено."""
        app = self.app
        t = app.raw_txt
        app.shell_box.close()
        t.mark_set('insert', f'{n}.end')
        t.see('insert')
        t.focus_set()
        app._canvas_highlight()
        self.draw()


def _middle(txt: tk.Text, line: int) -> float | None:
    info = txt.dlineinfo(f'{line}.0')
    if info is None:
        return None
    return info[1] + info[3] / 2
