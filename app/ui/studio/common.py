"""Общее для студий: временный документ для изолированного редактора и мелкие помощники."""

from __future__ import annotations

from PySide6.QtWidgets import QHBoxLayout, QMessageBox, QPushButton, QToolButton, QWidget

from app.core.document.model import ProjectDocument, ProjectMeta, Screen
from app.ui.workspace.editor import Editor


def scratch_document(main: ProjectDocument, screen: Screen) -> ProjectDocument:
    """Отдельный документ с одним экраном для изолированного редактирования (мастер компонента, иконка).
    Компоненты и ресурсы копируются, чтобы правки здесь не меняли проект до явного сохранения."""
    from app.core.commands import DocPatch
    doc = ProjectDocument(meta=ProjectMeta.from_dict(main.meta.to_dict()))
    snap = DocPatch.capture(main)
    snap["screens"] = [screen.to_dict()]
    DocPatch.restore(doc, snap)
    return doc


def editor_toolbar(editor: Editor, tools: list[tuple[str, str, str]], extra: list[QWidget] | None = None) -> QWidget:
    """Компактная панель: инструменты, отмена/повтор и дополнительные кнопки."""
    from app.ui.widgets import FlowLayout
    bar = QWidget()
    h = FlowLayout(bar, margin=6, spacing=4)  # при узком окне кнопки переносятся, а не сжимаются
    buttons = {}
    for key, glyph, tip in tools:
        b = QToolButton()
        b.setText(glyph)
        b.setToolTip(tip)
        b.setCheckable(True)
        b.clicked.connect(lambda _=False, k=key: (setattr(editor, "tool", k), editor.view_changed.emit()))
        buttons[key] = b
        h.addWidget(b)

    def sync():
        for k, b in buttons.items():
            b.setChecked(editor.tool == k)
    editor.view_changed.connect(sync)
    sync()
    for text, slot, tip in (("↶", editor.undo, "Отменить"), ("↷", editor.redo, "Повторить")):
        b = QToolButton()
        b.setText(text)
        b.setToolTip(tip)
        b.clicked.connect(slot)
        h.addWidget(b)
    for w in extra or []:
        h.addWidget(w)
    return bar


def ask_save(parent, what: str) -> str:
    """'save' | 'discard' | 'cancel'."""
    box = QMessageBox(QMessageBox.Icon.Question, "Несохранённые изменения", f"Сохранить изменения: {what}?",
                      parent=parent)
    save = box.addButton("Сохранить", QMessageBox.ButtonRole.AcceptRole)
    discard = box.addButton("Не сохранять", QMessageBox.ButtonRole.DestructiveRole)
    box.addButton("Отмена", QMessageBox.ButtonRole.RejectRole)
    box.exec()
    return "save" if box.clickedButton() is save else "discard" if box.clickedButton() is discard else "cancel"


def button(text: str, slot, tip: str = "", object_name: str = "") -> QPushButton:
    b = QPushButton(text)
    if tip:
        b.setToolTip(tip)
    if object_name:
        b.setObjectName(object_name)
    b.clicked.connect(slot)
    return b
