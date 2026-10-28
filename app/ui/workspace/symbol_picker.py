"""Окно «Значки Material»: ~3900 значков Google Material Symbols с поиском по-русски и по-английски,
стили «контурные / скруглённые / острые», заливка, размер. Картинки рисуются по мере прокрутки."""

from __future__ import annotations

from PySide6.QtCore import QAbstractListModel, QModelIndex, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QListView, QVBoxLayout,
)

from app.core.document.model import Node
from app.libraries import symbols
from app.ui.workspace.canvas import vector_path

ICON = 40


class SymbolModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: list[str] = []
        self.style, self.filled, self.color = "outlined", False, QColor("#EDEDED")
        self._cache: dict[tuple, QIcon] = {}

    def set_items(self, items: list[str]) -> None:
        self.beginResetModel()
        self.items = items
        self.endResetModel()

    def set_look(self, style: str, filled: bool) -> None:
        self.beginResetModel()
        self.style, self.filled = style, filled
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        name = self.items[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return name.replace("_", " ")
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{name} — {symbols.russian_name(name)}"
        if role == Qt.ItemDataRole.UserRole:
            return name
        if role == Qt.ItemDataRole.DecorationRole:
            key = (name, self.style, self.filled)
            icon = self._cache.get(key)
            if icon is None:
                icon = QIcon(render_symbol(name, self.style, self.filled, ICON, self.color))
                self._cache[key] = icon
            return icon
        return None


def render_symbol(name: str, style: str, filled: bool, size: int, color: QColor) -> QPixmap:
    pm = QPixmap(size, size)
    pm.fill(Qt.GlobalColor.transparent)
    d = symbols.path(name, style, filled)
    if d:
        n = Node(type="vector", x=0, y=0, w=size, h=size, path=d, vb_w=symbols.VIEWBOX, vb_h=symbols.VIEWBOX)
        p = QPainter(pm)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(color)
        p.drawPath(vector_path(n))
        p.end()
    return pm


class SymbolPicker(QDialog):
    """Выбор значка. После exec(): name, style, filled, size_dp."""

    def __init__(self, title: str = "Значки Material", parent=None, replace: bool = False):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.resize(760, 600)
        self.name: str | None = None
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Поиск: дом, корзина, стрелка, settings…")
        self.search.setClearButtonEnabled(True)
        top.addWidget(self.search, 1)
        self.style = QComboBox()
        for key, ru in symbols.STYLES.items():
            self.style.addItem(ru, key)
        top.addWidget(self.style)
        self.filled = QCheckBox("С заливкой")
        top.addWidget(self.filled)
        self.size = QComboBox()
        for dp in (16, 20, 24, 32, 40, 48, 64):
            self.size.addItem(f"{dp} dp", dp)
        self.size.setCurrentIndex(2)
        self.size.setToolTip("Размер значка на экране")
        self.size.setVisible(not replace)
        top.addWidget(self.size)
        lay.addLayout(top)
        self.count = QLabel()
        self.count.setObjectName("Muted")
        lay.addWidget(self.count)
        self.model = SymbolModel(self)
        self.view = QListView()
        self.view.setViewMode(QListView.ViewMode.IconMode)
        self.view.setIconSize(QSize(ICON, ICON))
        self.view.setGridSize(QSize(96, 84))
        self.view.setResizeMode(QListView.ResizeMode.Adjust)
        self.view.setMovement(QListView.Movement.Static)
        self.view.setUniformItemSizes(True)
        self.view.setWordWrap(True)
        self.view.setTextElideMode(Qt.TextElideMode.ElideRight)
        self.view.setModel(self.model)
        self.view.doubleClicked.connect(lambda _i: self._accept())
        lay.addWidget(self.view, 1)
        lay.addWidget(QLabel(f"Google Material Symbols {symbols.version()} · лицензия Apache 2.0"))
        bb = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        bb.button(QDialogButtonBox.StandardButton.Ok).setText("Заменить" if replace else "Добавить на экран")
        bb.button(QDialogButtonBox.StandardButton.Cancel).setText("Отмена")
        bb.accepted.connect(self._accept)
        bb.rejected.connect(self.reject)
        lay.addWidget(bb)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(150)
        self._timer.timeout.connect(self.refresh)
        self.search.textChanged.connect(self._timer.start)
        self.style.currentIndexChanged.connect(self._look)
        self.filled.toggled.connect(self._look)
        self.refresh()
        self.search.setFocus()

    def _look(self, *_):
        self.model.set_look(self.style.currentData(), self.filled.isChecked())

    def refresh(self) -> None:
        items = symbols.search(self.search.text())
        self.model.set_items(items)
        self.count.setText(f"Найдено значков: {len(items)}" if self.search.text().strip()
                           else f"Всего значков: {len(items)} — начните вводить название")
        if items:
            self.view.setCurrentIndex(self.model.index(0))

    def _accept(self) -> None:
        idx = self.view.currentIndex()
        if not idx.isValid():
            return
        self.name = self.model.items[idx.row()]
        self.accept()

    @property
    def style_key(self) -> str:
        return self.style.currentData()

    @property
    def is_filled(self) -> bool:
        return self.filled.isChecked()

    @property
    def size_dp(self) -> int:
        return self.size.currentData()
