"""Экраны картинками: PNG в нужном масштабе, PDF (страница — экран, векторно), иконка приложения из элемента."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QMarginsF, QRectF, QSizeF
from PySide6.QtGui import QColor, QImage, QPageLayout, QPageSize, QPainter, QPdfWriter
from PySide6.QtWidgets import QGraphicsScene

from app.core.document import tree
from app.core.document.model import Node, Screen
from app.ui.workspace.canvas import ArtboardItem, asset_lookup, build_scene

ICON_PX = 432  # иконка Android: 108 dp × 4 (xxxhdpi)


def _scene(screen: Screen, doc, color: str) -> QGraphicsScene:
    scene = QGraphicsScene()
    build_scene(scene, screen, color, asset_lookup(doc))
    return scene


def render_screen(screen: Screen, doc, color: str, scale: float = 1.0) -> QImage:
    """Экран целиком: фон экрана и все элементы, scale — во сколько раз крупнее пикселей макета."""
    w, h = max(1, round(screen.width * scale)), max(1, round(screen.height * scale))
    img = QImage(w, h, QImage.Format.Format_ARGB32)
    img.fill(QColor(color))
    p = QPainter(img)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                     | QPainter.RenderHint.SmoothPixmapTransform)
    _scene(screen, doc, color).render(p, QRectF(0, 0, w, h), QRectF(0, 0, screen.width, screen.height))
    p.end()
    return img


def widget_previews(doc, screens: list[Screen]) -> dict[str, bytes]:
    """Снимки виджетов рабочего стола на прозрачном фоне (PNG) — картинка в списке виджетов телефона."""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    out = {}
    for s in screens:
        img = QImage(s.width, s.height, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        scene = _scene(s, doc, "#00000000")
        for item in scene.items():
            if isinstance(item, ArtboardItem):
                item.setVisible(False)  # рамка холста не должна попасть в картинку на скруглённых углах
        p = QPainter(img)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                         | QPainter.RenderHint.SmoothPixmapTransform)
        scene.render(p, QRectF(0, 0, s.width, s.height), QRectF(0, 0, s.width, s.height))
        p.end()
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        out[s.id] = bytes(ba.data())
        out.update(widget_parts(doc, s))
    return out


def _png(img: QImage) -> bytes:
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(ba.data())


def widget_parts(doc, s: Screen, scale: float = 2.0) -> dict[str, bytes]:
    """Фигуры виджета, которые Glance не рисует (градиент, тень, обводка, овал), — картинкой без содержимого:
    {«part:<id>»: PNG}. Рисуется только сама фигура в своих границах, дети остаются элементами Glance."""
    import copy
    from app.exporters.glance import PART_PREFIX, needs_backdrop
    out = {}
    for n, _parent, _depth in tree.walk(s.nodes):
        if not needs_backdrop(n) or n.w < 1 or n.h < 1:
            continue
        alone = copy.deepcopy(n)
        alone.children = []
        alone.visible = True
        single = Screen(name="part", platform=s.platform, width=s.width, height=s.height, nodes=[alone])
        scene = QGraphicsScene()
        build_scene(scene, single, "#00000000", asset_lookup(doc))
        for item in scene.items():
            if isinstance(item, ArtboardItem):
                item.setVisible(False)
        w, h = max(1, round(n.w * scale)), max(1, round(n.h * scale))
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        p = QPainter(img)
        p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        scene.render(p, QRectF(0, 0, w, h), QRectF(n.x, n.y, n.w, n.h))
        p.end()
        out[PART_PREFIX + n.id] = _png(img)
    return out


def file_names(screens: list[Screen], ext: str) -> list[str]:
    """Имена файлов по экранам: «01 Главная.png», без недопустимых символов и повторов."""
    out, used = [], set()
    for i, s in enumerate(screens, 1):
        base = re.sub(r'[\\/:*?"<>|\n\r\t]+', " ", s.name).strip()[:80] or "Экран"
        name = f"{i:02d} {base}.{ext}"
        while name.lower() in used:
            name = f"{i:02d} {base} ({len(used)}).{ext}"
        used.add(name.lower())
        out.append(name)
    return out


def save_pngs(screens: list[Screen], doc, color: str, folder: str | Path, scale: float = 1.0) -> list[Path]:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    paths = []
    for s, name in zip(screens, file_names(screens, "png")):
        path = folder / name
        if not render_screen(s, doc, color, scale).save(str(path), "PNG"):
            raise OSError(f"Не удалось записать {path}")
        paths.append(path)
    return paths


def save_pdf(screens: list[Screen], doc, color: str, path: str | Path, title: str = "") -> int:
    """PDF: каждая страница — экран своего размера; элементы векторные (текст выделяется)."""
    if not screens:
        return 0
    w = QPdfWriter(str(path))
    w.setTitle(title)
    w.setCreator("App Design Studio")
    w.setResolution(96)

    def page_for(s: Screen):
        size = QPageSize(QSizeF(s.width * 72 / 96, s.height * 72 / 96), QPageSize.Unit.Point, s.name,
                         QPageSize.SizeMatchPolicy.ExactMatch)
        return QPageLayout(size, QPageLayout.Orientation.Portrait, QMarginsF(0, 0, 0, 0))

    w.setPageLayout(page_for(screens[0]))
    p = QPainter(w)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing)
    for i, s in enumerate(screens):
        if i:
            w.setPageLayout(page_for(s))
            w.newPage()
        target = QRectF(0, 0, w.width(), w.height())
        p.fillRect(target, QColor(color))
        _scene(s, doc, color).render(p, target, QRectF(0, 0, s.width, s.height))
    p.end()
    return len(screens)


def icon_image(screen: Screen, doc, color: str, node: Node, size: int = ICON_PX) -> QImage:
    """Элемент — квадратной картинкой для иконки: по центру, вписан целиком, вокруг прозрачно."""
    x, y, w, h = tree.bounds(node) or (node.x, node.y, node.w, node.h)
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(QColor(0, 0, 0, 0))
    single = Screen(name="icon", platform=screen.platform, width=screen.width, height=screen.height,
                    nodes=[node])  # только сам элемент, без фона экрана и соседей
    scene = QGraphicsScene()
    build_scene(scene, single, color, asset_lookup(doc))
    for item in scene.items():
        if isinstance(item, ArtboardItem):
            item.setVisible(False)  # фон экрана не рисуется — вокруг элемента прозрачно
    side = max(w, h)
    src = QRectF(x - (side - w) / 2, y - (side - h) / 2, side, side)
    p = QPainter(img)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
    scene.render(p, QRectF(0, 0, size, size), src)
    p.end()
    return img


def icon_background(img: QImage, node: Node) -> str:
    """Цвет подложки адаптивной иконки: заливка элемента или белый."""
    c = img.pixelColor(img.width() // 2, 2)
    if c.alpha() > 200:
        return c.name().upper()
    return (node.fill[:7] if node.fill else "#FFFFFF").upper()
