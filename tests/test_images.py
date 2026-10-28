"""1.11: картинки и фото — вставка из файла и перетаскиванием, заглушки, вписать / заполнить, маски, код Android."""

import pytest
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter
from PySide6.QtWidgets import QApplication, QMessageBox

from app.context import AppContext
from app.core.document import tree
from app.core.document.model import Node
from app.engines.material.color import scheme
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.ui.shell.main_window import MainWindow
from app.ui.themes.fusion_amoled import apply_theme
from app.ui.workspace.canvas import _fit_rects, paint_node
from app.ui.workspace.images import PLACEHOLDERS, placeholder_asset, read_image
from tests.conftest import make_spec


def _png(path, w, h, color="#FF0000"):
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    img.save(str(path), "PNG")
    return path


def test_read_image_and_placeholders(tmp_path):
    p = _png(tmp_path / "фото.png", 400, 200)
    assert read_image(p.read_bytes(), "фото.png") == ("png", 400, 200)
    with pytest.raises(ValueError, match="формат"):
        read_image(b"not an image", "x.png")
    sch = scheme("#2F7BFF", True)
    shas = set()
    for k in PLACEHOLDERS:
        a, data, size = placeholder_asset(k, sch)
        assert a.redistribution == "allowed" and a.ext == "png" and size == (960, 720)
        shas.add(a.sha256)
    assert len(shas) == len(PLACEHOLDERS)                                       # все заглушки разные
    assert _fit_rects(QRectF(0, 0, 100, 100), 400, 200, "cover")[1] == QRectF(100, 0, 200, 200)
    dst, _ = _fit_rects(QRectF(0, 0, 100, 100), 400, 200, "contain")
    assert dst == QRectF(0, 25, 100, 50)
    assert Node.from_dict({**Node(type="image", fit="cover").to_dict()}).fit == "cover"


@pytest.fixture
def win(qtbot, paths, projects_dir, monkeypatch):
    apply_theme(QApplication.instance())
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: QMessageBox.StandardButton.Ok)
    ctx = AppContext.create(paths)
    ctx.settings.set("general/projects_dir", str(projects_dir))
    w = MainWindow(ctx)

    def discard(x):
        x.project_page.mark_clean()
        x.dirty = False
    qtbot.addWidget(w, before_close_func=discard)
    w.show()
    _, path = ctx.service.create(make_spec(projects_dir, title="Фото"))
    w.open_project(str(path))
    yield w
    ctx.close()


def test_insert_drop_replace_mask_and_export(qtbot, win, tmp_path):
    page, ed = win.project_page, win.project_page.editor
    s = ed.screen()
    wide = _png(tmp_path / "широкое.png", 1600, 800)
    page.image_dialog(str(wide))
    img = ed.selected_nodes()[0]
    assert img.type == "image" and img.fit == "cover" and img.w == pytest.approx(s.width * 0.6)
    assert img.h == pytest.approx(img.w / 2)                                    # пропорции файла
    page.image_dialog(str(wide))                                                # тот же файл — без дубликата
    assert len(ed.doc.assets) == 1
    page.drop_images([str(_png(tmp_path / "a.png", 300, 300, "#00FF00")), str(tmp_path / "нет.png")], 100, 200)
    dropped = ed.screen().nodes[-1]
    assert (dropped.x, dropped.y) == (100, 200) and len(ed.doc.assets) == 2
    # заглушка вместо контейнера-фото: то же место, размер и скругление
    ed.add_template_screen("product")
    photo = next(n for n, _, _ in tree.walk(ed.screen().nodes) if n.name == "Фото товара")
    geo = (photo.x, photo.y, photo.w, photo.h, photo.radius)
    ed.select([photo.id])
    page.placeholder_photo("product")
    new = ed.selected_nodes()[0]
    assert new.type == "image" and (new.x, new.y, new.w, new.h, new.radius) == pytest.approx(geo)
    assert new.sizing_h == "fill"                                               # в столбце — на всю ширину
    page.placeholder_photo("person")                                            # выделена картинка — меняется файл
    assert tree.find(ed.screen(), new.id)[0].name == new.name and len(ed.doc.assets) == 4
    page.inspector._image_mask("circle")
    c = tree.find(ed.screen(), new.id)[0]
    assert c.w == c.h and c.radius == pytest.approx(c.w / 2)
    # отрисовка: круг — углы прозрачные, центр закрашен
    canvas = QImage(int(c.w), int(c.h), QImage.Format.Format_ARGB32)
    canvas.fill(QColor(0, 0, 0, 0))
    p = QPainter(canvas)
    p.translate(-c.x, -c.y)
    from app.ui.workspace.canvas import asset_lookup
    paint_node(p, c, asset_lookup(ed.doc))
    p.end()
    assert canvas.pixelColor(1, 1).alpha() == 0 and canvas.pixelColor(int(c.w / 2), int(c.h / 2)).alpha() == 255
    page.inspector.img_fit.setCurrentIndex(page.inspector.img_fit.findData("contain"))
    assert tree.find(ed.screen(), new.id)[0].fit == "contain"
    f = build_package(ed.doc, ExportOptions()).files
    base = f"{ROOT}/app/src/main/java/{package_name(ed.doc.meta.title).replace('.', '/')}"
    src = next(v.decode() for k, v in f.items() if k.startswith(base + "/ui/screens/Tovar"))
    assert "contentScale = ContentScale.Fit" in src and ".clip(CircleShape)" in src
    assert any(k.startswith(f"{ROOT}/app/src/main/res/drawable/") and k.endswith(".png") for k in f)
