"""Диагностика раскладки и проверка адаптивности (телефон / планшет / окно Windows)."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QPushButton, QVBoxLayout, QWidget,
)

from app.engines.layout import resize_screen
from app.ui.widgets import label
from app.ui.workspace.canvas import render_thumbnail
from app.ui.workspace.editor import Editor

ROLE_ID = Qt.ItemDataRole.UserRole
SEVERITY = {"warning": "⚠", "info": "ℹ"}
RESPONSIVE_SIZES = [("Телефон (компактный)", 720, 1600), ("Телефон", 1080, 2400), ("Планшет", 1600, 2560),
                    ("Окно Windows", 1280, 800)]


class DiagnosticsPanel(QWidget):
    def __init__(self, editor: Editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        lay = QVBoxLayout(self)
        lay.setContentsMargins(8, 6, 8, 6)
        self.summary = label("", "Muted")
        lay.addWidget(self.summary)
        self.list = QListWidget()
        self.list.setWordWrap(True)
        self.list.itemClicked.connect(self._select)
        lay.addWidget(self.list, 1)
        editor.document_changed.connect(self.refresh)
        editor.screen_changed.connect(self.refresh)

    def refresh(self) -> None:
        self.list.clear()
        diags = self.editor.diagnostics
        for d in diags:
            it = QListWidgetItem(f"{SEVERITY.get(d.severity, '•')}  {d.message}")
            it.setData(ROLE_ID, d.node_id)
            it.setToolTip("Нажмите, чтобы выделить элемент")
            self.list.addItem(it)
        warnings = sum(1 for d in diags if d.severity == "warning")
        self.summary.setText("Замечаний к раскладке нет" if not diags else
                             f"Предупреждений: {warnings}, подсказок: {len(diags) - warnings}")

    def _select(self, item: QListWidgetItem) -> None:
        nid = item.data(ROLE_ID)
        if nid:
            self.editor.select_any([nid])


class ResponsiveDialog(QDialog):
    """Текущий экран, перестроенный под разные размеры по привязкам и Auto Layout. Документ не меняется."""

    def __init__(self, editor: Editor, parent=None):
        super().__init__(parent)
        self.editor = editor
        self.setWindowTitle("Проверка адаптивности")
        self.resize(1300, 760)
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        s = editor.screen()
        root.addWidget(label(f"Экран «{s.name}» на разных размерах", "H1"))
        root.addWidget(label("Пересчёт по привязкам и Auto Layout. Это проверка — исходный экран не изменяется. "
                             "Отрисовка Android — приближение, не точный рендер Jetpack Compose.", "Muted", wrap=True))
        grid = QGridLayout()
        grid.setHorizontalSpacing(16)
        self.results = []
        for col, (name, w, h) in enumerate(RESPONSIVE_SIZES):
            clone, diags = resize_screen(s, w, h, editor.engine)
            self.results.append((name, w, h, clone, diags))
            pic = QLabel()
            pic.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pic.setPixmap(render_thumbnail(clone, editor.artboard_color(), 290, 420))
            grid.addWidget(label(f"{name}\n{w} × {h}", "H2"), 0, col)
            grid.addWidget(pic, 1, col)
            lst = QListWidget()
            lst.setWordWrap(True)
            lst.setMinimumHeight(140)
            if not diags:
                lst.addItem("✓ Замечаний нет")
            for d in diags:
                it = QListWidgetItem(f"{SEVERITY.get(d.severity, '•')} {d.message}")
                it.setToolTip(d.message)
                lst.addItem(it)
            grid.addWidget(lst, 2, col)
        root.addLayout(grid, 1)
        row = QHBoxLayout()
        row.addStretch()
        close = QPushButton("Закрыть")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        root.addLayout(row)
