"""1.26: Android до конца — свои шрифты, SVG → VectorDrawable, анимации размера / цвета / скругления / шрифта,
подписанная сборка для Google Play."""

import hashlib
from pathlib import Path

import pytest

from app.core.document.behavior import Animation, Interaction, Keyframe, Track
from app.core.document.model import Asset, Node
from app.exporters import apk_builder
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.exporters.fontinfo import weight_italic
from app.exporters.vector_drawable import svg_to_vector

FONTS = Path("C:/Windows/Fonts")
SVG = (b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100"><circle cx="50" cy="50" r="40" fill="#FFB300"/>'
       b'<path d="M10 10 L30 10 L30 30 Z" fill="#E53935" fill-opacity="0.5" stroke="#000000" stroke-width="2" fill-rule="evenodd"/>'
       b'<script>alert(1)</script></svg>')


def _screen_src(files, doc):
    base = f"{ROOT}/app/src/main/java/{package_name(doc.meta.title).replace('.', '/')}"
    return next(v.decode() for k, v in files.items() if k.startswith(f"{base}/ui/screens/")), base


@pytest.fixture
def doc(qapp, paths, projects_dir):
    from app.context import AppContext
    from tests.conftest import make_spec
    ctx = AppContext.create(paths)
    d, _ = ctx.service.create(make_spec(projects_dir, title="Шрифты"))
    yield d
    ctx.close()


def test_font_weight_from_file():
    if not (FONTS / "arialbd.ttf").exists():
        pytest.skip("нет системных шрифтов Windows")
    assert weight_italic((FONTS / "arial.ttf").read_bytes()) == (400, False)
    assert weight_italic((FONTS / "arialbd.ttf").read_bytes()) == (700, False)
    assert weight_italic((FONTS / "ariali.ttf").read_bytes())[1] is True
    assert weight_italic(b"not a font") == (400, False)


def test_svg_to_vector_drawable():
    xml = svg_to_vector(SVG)
    assert xml.startswith('<?xml') and 'android:viewportWidth="100.0"' in xml
    assert xml.count("<path ") == 2 and 'android:fillColor="#FFFFB300"' in xml
    assert 'android:fillColor="#80E53935"' in xml or 'android:fillColor="#7FE53935"' in xml and 'android:strokeColor="#FF000000"' in xml   # альфа — вперёд
    assert 'android:fillType="evenOdd"' in xml and "alert" not in xml                            # скрипт вычищен
    assert svg_to_vector(b"<svg></svg>") is None and svg_to_vector(b"broken") is None


def test_fonts_svg_and_animations_in_android(doc):
    s = doc.screens[0]
    if (FONTS / "arialbd.ttf").exists():
        for fn in ("arial.ttf", "arialbd.ttf"):
            data = (FONTS / fn).read_bytes()
            a = Asset(kind="font", name=fn, ext="ttf", sha256=hashlib.sha256(data).hexdigest(), size=len(data),
                      family="Arial")
            doc.assets.append(a)
            doc.asset_data[a.id] = data
    logo = Asset(kind="image", name="logo.svg", ext="svg", sha256=hashlib.sha256(SVG).hexdigest(), size=len(SVG))
    doc.assets.append(logo)
    doc.asset_data[logo.id] = SVG
    title = Node(type="text", name="Заголовок", text="Привет", font_family="Arial", font_weight=700, fill="",
                 x=10, y=10, w=300, h=40)
    img = Node(type="image", name="Лого", asset_id=logo.id, x=10, y=60, w=100, h=100, fill="")
    bar = Node(type="rect", name="Полоса", x=10, y=200, w=60, h=40, fill="#6750A4", radius=4)
    s.nodes += [title, img, bar]
    anim = Animation(name="Показ", screen_id=s.id, duration=800, tracks=[
        Track(node_id=bar.id, prop="w", keyframes=[Keyframe(0, 60), Keyframe(800, 300)]),
        Track(node_id=bar.id, prop="fill", keyframes=[Keyframe(0, "#6750A4"), Keyframe(800, "#2E7D32")]),
        Track(node_id=bar.id, prop="radius", keyframes=[Keyframe(0, 4), Keyframe(800, 20)]),
        Track(node_id=title.id, prop="font_size", keyframes=[Keyframe(0, 20), Keyframe(800, 40)]),
        Track(node_id=title.id, prop="text_color", keyframes=[Keyframe(0, "#000000"), Keyframe(800, "#E53935")])])
    doc.animations.append(anim)
    doc.interactions.append(Interaction(screen_id=s.id, trigger="screen_open",
                                        actions=[{"type": "play_animation", "animation_id": anim.id}]))
    files = build_package(doc, ExportOptions()).files
    src, base = _screen_src(files, doc)
    res = f"{ROOT}/app/src/main/res"
    assert f"{res}/drawable/logo.xml" in files and "painterResource(R.drawable.logo)" in src
    if (FONTS / "arialbd.ttf").exists():
        assert f"{res}/font/font_arial.ttf" in files and f"{res}/font/font_arialbd.ttf" in files
        fonts = files[f"{base}/ui/theme/Fonts.kt"].decode()
        assert "val ArialFont = FontFamily(" in fonts and "FontWeight(400)" in fonts and "FontWeight(700)" in fonts
        assert "fontFamily = ArialFont" in src and f"import {package_name(doc.meta.title)}.ui.theme.ArialFont" in src
    for code in (".value.dp)", "androidx.compose.animation.Animatable(Color(0xFF6750A4))",
                 "RoundedCornerShape(", ".value.sp", "color = anim"):
        assert code in src, code
    assert "// TODO: анимации" not in src and "TODO: изображение" not in src


def test_release_signing(tmp_path, doc):
    files = build_package(doc, ExportOptions()).files
    gradle = files[f"{ROOT}/app/build.gradle.kts"].decode()
    assert 'rootProject.file("release.properties")' in gradle and 'create("upload")' in gradle
    assert 'versionCode = (release.getProperty("versionCode") ?: "1").toInt()' in gradle
    assert "/release.properties" in files[f"{ROOT}/.gitignore"].decode()
    _exe, args = apk_builder.build_command(apk_builder.Toolchain(gradle=Path("gradle.bat")), tmp_path, release=True)
    assert "bundleRelease" in args and "assembleRelease" in args
    assert apk_builder.aab_path(tmp_path).name == "app-release.aab"
    t = apk_builder.find_toolchain()
    if t.java_home is None:
        pytest.skip("нет JDK (keytool)")
    keys = tmp_path / "keys"
    key = apk_builder.signing_key(t, keys, "com.design.test")
    assert key.store.exists() and len(key.password) >= 20
    again = apk_builder.signing_key(t, keys, "com.design.test")              # второй раз — тот же ключ
    assert again.password == key.password
    project = tmp_path / "proj"
    project.mkdir()
    assert apk_builder.prepare_release(project, again, keys, "com.design.test", "1.2") == 1
    assert apk_builder.prepare_release(project, again, keys, "com.design.test", "1.3") == 2
    props = (project / "release.properties").read_text(encoding="utf-8")
    assert "versionCode=2" in props and "versionName=1.3" in props and "\\" not in props
    assert apk_builder.signing_key(t, keys, "com.design.test").version_code == 2   # номер помнится
