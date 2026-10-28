"""Текст не выходит за обрезку контейнера (прокрутка, скругление): найдено тестировщиком в 1.19 —
подписи легенды вылезали под нижнюю панель экрана «Статистика»."""

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QGraphicsScene

from app.core.document.model import Node, Screen
from app.ui.workspace.canvas import build_scene


def test_text_clipped_by_parent_frame(qapp):
    text = Node(type="text", text="████████", x=10, y=60, w=80, h=40, fill="", font_size=30, text_color="#FF0000")
    frame = Node(type="frame", x=0, y=0, w=100, h=50, fill="#FFFFFF", clip=True, children=[text])
    s = Screen(name="s", platform="windows", width=100, height=120, nodes=[frame])
    scene = QGraphicsScene()
    build_scene(scene, s, "#000000")
    img = QImage(100, 120, QImage.Format.Format_ARGB32)
    img.fill(QColor("#000000"))
    p = QPainter(img)
    scene.render(p, QRectF(0, 0, 100, 120), QRectF(0, 0, 100, 120))
    p.end()
    reds = [(x, y) for x in range(100) for y in range(50, 120) if img.pixelColor(x, y).red() > 150
            and img.pixelColor(x, y).green() < 80]
    assert not reds                                                      # ниже контейнера текста нет
