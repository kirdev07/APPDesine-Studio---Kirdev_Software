"""1.7: больше элементов — значки, вход и регистрация, формы, профиль, магазин, состояния; поле пароля в Compose."""

from app.core.document import tree
from app.exporters.ai_export import ExportOptions, build_package
from app.exporters.android_project import ROOT, package_name
from app.libraries import components
from app.libraries.components_more import SPECS as MORE
from app.libraries.m3_icons import ICONS
from tests.test_android_export import _balanced
from tests.test_preview import doc_with_form


def test_catalog_is_bigger_and_grouped():
    assert len(ICONS) >= 75
    specs = components.specs_for("android")
    cats = {s.category for s in specs}
    assert {"Вход и регистрация", "Поля", "Профиль и люди", "Магазин", "Состояния", "Значки"} <= cats
    assert len(specs) >= 140
    kinds = [s.kind for s in specs]
    assert len(kinds) == len(set(kinds))                                     # без повторов
    # порядок галереи: сначала компоненты, потом дополнительные, значки — в конце
    first_icon = next(i for i, s in enumerate(specs) if s.category == "Значки")
    assert all(s.category == "Значки" for s in specs[first_icon:])


def test_new_components_build_with_roles_and_no_brand_logos():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    for sp in MORE:
        n = components.build(sp.kind, s, doc.meta.appearance)
        assert n.role.startswith("m3."), sp.kind
        assert n.w > 0 and n.h > 0
    g = components.build("m3_sign_in_google", s, doc.meta.appearance)
    badge = g.children[0]
    assert badge.children[0].type == "text" and badge.children[0].text == "G"   # буква, а не логотип
    assert "Войти через Google" in [d.text for d in tree.descendants(g) if d.type == "text"]


def test_password_field_is_real_compose_field():
    doc, _ = doc_with_form()
    s = doc.screens[0]
    s.nodes.append(components.build("m3_password_field", s, doc.meta.appearance))
    s.nodes.append(components.build("m3_product_card", s, doc.meta.appearance))
    f = build_package(doc, ExportOptions()).files
    base = f"{ROOT}/app/src/main/java/{package_name(doc.meta.title).replace('.', '/')}"
    src = f[f"{base}/ui/screens/FormaScreen.kt"].decode()
    assert _balanced(src)
    from tests.conftest import inline_strings
    src = inline_strings(src, f)
    for code in ("OutlinedTextField(", "PasswordVisualTransformation()", "VisualTransformation.None",
                 'placeholder = { Text("Пароль") }', 'supportingText = { Text("Не меньше 8 символов") }',
                 "trailingIcon = {", "mutableStateOf(false)", "Показать пароль"):
        assert code in src, code
    assert "Беспроводные наушники" in src and "В корзину" in src           # карточка товара — раскладкой
