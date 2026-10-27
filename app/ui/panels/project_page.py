"""Открытый проект. На этапе 1 — свойства проекта и список экранов; холст появится на этапе 2."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLineEdit, QListWidget, QPlainTextEdit, QVBoxLayout, QWidget

from app.core.document.model import ProjectDocument
from app.ui.widgets import format_date, label, panel, platforms_text, stage_badge


class ProjectPage(QWidget):
    edited = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Page")
        self.doc: ProjectDocument | None = None
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        left, llay = panel()
        left.setFixedWidth(300)
        llay.addWidget(label("Экраны", "H2"))
        self.screens = QListWidget()
        llay.addWidget(self.screens, 1)
        root.addWidget(left)

        center, clay = panel()
        head = QHBoxLayout()
        head.addWidget(label("Рабочая область", "H2"))
        head.addStretch()
        head.addWidget(stage_badge(2))
        clay.addLayout(head)
        note = label("Холст, слои, выделение, сетка, привязки и undo/redo будут реализованы на этапе 2.\n"
                     "Сейчас доступны свойства проекта, сохранение (Ctrl+S) и автосохранение.", "Muted", wrap=True)
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        clay.addStretch()
        clay.addWidget(note)
        clay.addStretch()
        root.addWidget(center, 1)

        right, rlay = panel()
        right.setFixedWidth(320)
        rlay.addWidget(label("Свойства проекта", "H2"))
        form = QFormLayout()
        self.title = QLineEdit()
        self.title.textEdited.connect(self._on_title)
        form.addRow("Название", self.title)
        self.platforms = label("")
        form.addRow("Платформы", self.platforms)
        self.created = label("")
        form.addRow("Создан", self.created)
        self.appearance = label("", wrap=True)
        form.addRow("Оформление", self.appearance)
        rlay.addLayout(form)
        rlay.addWidget(label("Описание", "Muted"))
        self.desc = QPlainTextEdit()
        self.desc.textChanged.connect(self._on_desc)
        rlay.addWidget(self.desc, 1)
        root.addWidget(right)

    def set_document(self, doc: ProjectDocument) -> None:
        self.doc = doc
        m = doc.meta
        self.title.setText(m.title)
        self.desc.blockSignals(True)
        self.desc.setPlainText(m.description)
        self.desc.blockSignals(False)
        self.platforms.setText(platforms_text(m.platforms))
        self.created.setText(format_date(m.created_at))
        a = m.appearance
        self.appearance.setText(f"тема {a.theme}, акцент {a.accent}, {a.font_family}, радиус {a.corner_radius} dp")
        self.screens.clear()
        for s in doc.screens:
            self.screens.addItem(f"{s.name}\n{s.width} × {s.height} · {s.orientation}")

    def _on_title(self, text: str) -> None:
        if self.doc and text.strip():
            self.doc.meta.title = text.strip()
            self.edited.emit()

    def _on_desc(self) -> None:
        if self.doc:
            self.doc.meta.description = self.desc.toPlainText()
            self.edited.emit()
