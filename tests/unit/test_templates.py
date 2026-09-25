from src.enums import TemplatePackId
from src.templates import TEMPLATES, get_template_pack_id


def test_get_template_pack_id_deterministic():
    pack1 = get_template_pack_id(123)
    pack2 = get_template_pack_id(123)
    assert pack1 == pack2
    assert isinstance(pack1, TemplatePackId)


def test_all_packs_in_templates():
    for pack_id in TemplatePackId:
        assert pack_id in TEMPLATES
        assert len(TEMPLATES[pack_id]) > 0
