"""Галерея компонентов: плитки с картинкой каждой заготовки, категории, поиск, перетаскивание на холст.

Щелчок — добавить на экран; перетаскивание — добавить в точку; правая кнопка — «Добавить» или «Заменить
выделенное». Картинки рисуются тем же движком, что и холст, в цветах оформления проекта, и кешируются.
"""

from __future__ import annotations

import textwrap

from PySide6.QtCore import QByteArray, QMimeData, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView, QComboBox, QDialog, QDialogButtonBox, QGraphicsScene, QHBoxLayout, QLineEdit, QListWidget,
    QListWidgetItem, QMenu, QVBoxLayout, QWidget,
)

from app.core.document import tree
from app.core.document.model import Screen
from app.libraries import components
from app.ui.workspace.canvas import build_scene

MIME = "application/x-ads-component"
ROLE_KIND = Qt.ItemDataRole.UserRole
THUMB = QSize(96, 64)   # две колонки плиток даже в узкой панели
_cache: dict[tuple, QPixmap] = {}


def thumbnail(kind: str, screen: Screen, appearance, engine, artboard: str) -> QPixmap:
    """Картинка заготовки: строится узел, раскладывается движком и рисуется в рамку THUMB."""
    key = (kind, screen.platform, screen.device_id, screen.width, appearance.theme, appearance.accent,
           appearance.font_family, artboard)
    hit = _cache.get(key)
    if hit is not None:
        return hit
    tmp = Screen(name="превью", platform=screen.platform, width=screen.width, height=screen.height,
                 device_id=screen.device_id)
    node = components.build(kind, tmp, appearance)
    tmp.nodes = [node]
    changes, _ = engine.layout_screen(tmp)
    m = tree.node_map(tmp)
    for nid, props in changes.items():
        for k, v in props.items():
            setattr(m[nid], k, v)
    x, y, w, h = tree.bounds(node)
    pm = QPixmap(THUMB)
    pm.fill(QColor(artboard))
    scene = QGraphicsScene()
    build_scene(scene, tmp, artboard)
    pad = max(w, h) * 0.06 + 4
    src = QRectF(x - pad, y - pad, w + 2 * pad, h + 2 * pad)
    p = QPainter(pm)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    scene.render(p, QRectF(2, 2, THUMB.width() - 4, THUMB.height() - 4), src, Qt.AspectRatioMode.KeepAspectRatio)
    p.end()
    _cache[key] = pm
    return pm


def _two_lines(name: str, width: int = 15) -> str:
    """Подпись плитки в две строки по словам: в плитке нет места для длинной строки, многоточие хуже."""
    lines = textwrap.wrap(name, width) or [name]
    if len(lines) > 2:
        lines = [lines[0], " ".join(lines[1:])]
    return "\n".join(lines)


class _Tiles(QListWidget):
    """Плитки с перетаскиванием: в данных — вид заготовки."""

    def mimeData(self, items):
        md = QMimeData()
        if items:
            md.setData(MIME, QByteArray(items[0].data(ROLE_KIND).encode("utf-8")))
        return md

    def mimeTypes(self):
        return [MIME]


class ComponentGallery(QWidget):
    add_requested = Signal(str)
    replace_requested = Signal(str)

    def __init__(self, editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)
        row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск…")
        self.search.setToolTip("Поиск компонента: кнопка, переключатель, значок…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        row.addWidget(self.search, 1)
        self.category = QComboBox()
        self.category.setFixedWidth(104)
        self.category.setToolTip("Категория компонентов")
        self.category.currentIndexChanged.connect(self.apply_filter)
        row.addWidget(self.category)
        lay.addLayout(row)
        self.tiles = _Tiles()
        self.tiles.setViewMode(QListWidget.ViewMode.IconMode)
        self.tiles.setIconSize(THUMB)
        self.tiles.setGridSize(QSize(THUMB.width() + 10, THUMB.height() + 38))
        self.tiles.setResizeMode(QListWidget.ResizeMode.Adjust)
        self.tiles.setMovement(QListWidget.Movement.Static)
        self.tiles.setWordWrap(True)
        self.tiles.setTextElideMode(Qt.TextElideMode.ElideNone)
        self.tiles.setSpacing(4)
        self.tiles.setDragEnabled(True)
        self.tiles.setDragDropMode(QAbstractItemView.DragDropMode.DragOnly)
        self.tiles.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.tiles.setStyleSheet("QListWidget{background:transparent;border:none}"
                                 "QListWidget::item{border-radius:6px;padding:2px;color:#D0D0D0}"
                                 "QListWidget::item:hover{background:#1A1A1A}"
                                 "QListWidget::item:selected{background:#14233D;border:1px solid #2F7BFF}")
        self.tiles.setToolTip("Щелчок — добавить на экран, перетаскивание — поставить в нужное место, "
                              "правая кнопка — заменить выделенный элемент")
        self.tiles.itemClicked.connect(lambda it: self.add_requested.emit(it.data(ROLE_KIND)))
        self.tiles.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tiles.customContextMenuRequested.connect(self._menu)
        lay.addWidget(self.tiles, 1)

    def rebuild(self) -> None:
        self.tiles.clear()
        s = self.editor.screen()
        doc = self.editor.doc
        if s is None or doc is None:
            return
        specs = components.specs_for(s.platform)
        cats = []
        for sp in specs:
            if sp.category not in cats:
                cats.append(sp.category)
        current = self.category.currentText()
        self.category.blockSignals(True)
        self.category.clear()
        self.category.addItem("Все")
        self.category.addItems(cats)
        self.category.setCurrentText(current if current in cats else "Все")
        self.category.blockSignals(False)
        art = self.editor.artboard_color()
        for sp in specs:
            name = sp.name.replace("Значок «", "").rstrip("»") if sp.category == "Значки" else sp.name
            it = QListWidgetItem(QIcon(thumbnail(sp.kind, s, doc.meta.appearance, self.editor.engine, art)),
                                 _two_lines(name))
            it.setData(Qt.ItemDataRole.UserRole + 2, name)
            it.setData(ROLE_KIND, sp.kind)
            it.setData(Qt.ItemDataRole.UserRole + 1, f"{sp.category} {sp.name}".lower())
            it.setToolTip(f"{sp.category} · {sp.name}\nЩелчок — добавить, перетаскивание — поставить в точку")
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignTop)
            self.tiles.addItem(it)
        self.apply_filter()

    def apply_filter(self, *_):
        words = self.search.text().lower().split()
        cat = self.category.currentText()
        for i in range(self.tiles.count()):
            it = self.tiles.item(i)
            hay = it.data(Qt.ItemDataRole.UserRole + 1)
            ok = all(w in hay for w in words) and (cat in ("", "Все") or hay.startswith(cat.lower() + " "))
            it.setHidden(not ok)

    def visible_names(self) -> list[str]:
        return [self.tiles.item(i).data(Qt.ItemDataRole.UserRole + 2) for i in range(self.tiles.count())
                if not self.tiles.item(i).isHidden()]

    def _menu(self, pos) -> None:
        it = self.tiles.itemAt(pos)
        if it is None:
            return
        kind = it.data(ROLE_KIND)
        m = QMenu(self)
        m.addAction("Добавить на экран", lambda: self.add_requested.emit(kind))
        a = m.addAction("Заменить выделенный элемент этим", lambda: self.replace_requested.emit(kind))
        a.setEnabled(bool(self.editor.selection))
        m.exec(self.tiles.viewport().mapToGlobal(pos))


class PickComponentDialog(QDialog):
    """Выбор заготовки по картинкам: щелчок по плитке — выбрать и закрыть."""

    def __init__(self, editor, title: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(640, 560)
        self.kind: str | None = None
        lay = QVBoxLayout(self)
        self.gallery = ComponentGallery(editor)
        self.gallery.tiles.setDragEnabled(False)
        self.gallery.tiles.setToolTip("Щелчок — выбрать")
        self.gallery.add_requested.connect(self._choose)
        self.gallery.replace_requested.connect(self._choose)
        lay.addWidget(self.gallery, 1)
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self.gallery.rebuild()
        self.gallery.search.setFocus()

    def _choose(self, kind: str) -> None:
        self.kind = kind
        self.accept()
