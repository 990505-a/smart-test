"""知识库注册表（services/rag_kbs.py）单测。

背景：LightRAG 官方**没有**"按请求切库"的能力——``/query``、``/documents/*`` 的
请求体里没有 workspace 字段（可用 GET /openapi.json 自查），一个进程就是一个库。
所以"两个项目别混在一起"= 两个实例 + 两个 workspace，注册表就是这份清单的事实源：
启动器按它拉起进程，平台（FastAPI）按它选地址。

这些用例把三件容易写错的事钉住：默认库必须与升级前的单库行为**逐字节兼容**
（workspace 空、端口 5014、服务名 lightrag）、key 与端口要校验、坏文件不能把
服务打挂。
"""

from __future__ import annotations

import json

import pytest

from src.app.core.config import settings
from src.app.services import rag_kbs


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """把注册表指到临时目录：单测绝不能碰 workspace/default/rag_kbs.json。"""
    path = tmp_path / "rag_kbs.json"
    monkeypatch.setattr(rag_kbs, "kbs_path", lambda space_id=None: path)
    rag_kbs.invalidate_cache()
    yield path
    rag_kbs.invalidate_cache()


def test_missing_file_seeds_from_settings(isolated):
    """没有注册表文件时 = 升级前的单库行为：:5014、workspace 空、服务名 lightrag。"""
    kbs = rag_kbs.load_kbs()
    assert [k.key for k in kbs] == ["default"]
    kb = kbs[0]
    assert kb.port == 5014
    assert kb.workspace == ""          # 空 workspace = LightRAG 的全局命名空间
    assert kb.service_name == "lightrag"
    assert kb.data_dir == settings.lightrag_working_dir
    assert kb.base_url == "http://127.0.0.1:5014"


def test_save_and_reload_round_trip(isolated):
    rag_kbs.save_kbs([
        {"key": "default", "label": "默认知识库", "port": 5014},
        {"key": "ruoyi", "label": "若依后台", "port": 5021, "description": "后台需求文档"},
    ])
    assert isolated.is_file()
    raw = json.loads(isolated.read_text(encoding="utf-8"))
    assert [row["key"] for row in raw["kbs"]] == ["default", "ruoyi"]
    # 派生字段不写进文件（避免两处事实源）
    assert "workspace" not in raw["kbs"][1]

    kbs = rag_kbs.load_kbs()
    assert [k.key for k in kbs] == ["default", "ruoyi"]
    ruoyi = kbs[1]
    assert ruoyi.workspace == "ruoyi"          # 非默认库：workspace = key
    assert ruoyi.data_dir.endswith("/rag/ruoyi")
    assert ruoyi.inputs_dir == "inputs/ruoyi"
    assert ruoyi.service_name == "lightrag-ruoyi"
    assert ruoyi.settings_url.endswith("/webui/rag-settings.html")


def test_workspace_is_sanitized_like_lightrag_does(isolated):
    """连字符在 LightRAG 里会被换成下划线（它自己的 sanitize），先对齐再暴露给用户。"""
    rag_kbs.save_kbs([{"key": "ruoyi-web", "label": "ruoyi 前端", "port": 5022}])
    assert rag_kbs.load_kbs()[0].workspace == "ruoyi_web"


def test_corrupt_file_degrades_to_default(isolated):
    """坏 JSON 不能让知识库在控制台上消失（启动器与平台都读这个文件）。"""
    isolated.write_text("{ 这不是 JSON", encoding="utf-8")
    kbs = rag_kbs.load_kbs()
    assert [k.key for k in kbs] == ["default"]
    assert kbs[0].port == 5014


def test_validate_rejects_the_usual_mistakes(isolated):
    errors = rag_kbs.validate([])
    assert errors and "至少" in errors[0]

    cases = [
        ([{"key": "Ruoyi", "port": 5021}], "小写"),
        ([{"key": "a b", "port": 5021}], "不合法"),
        ([{"key": "a", "port": 5021}, {"key": "a", "port": 5022}], "重复"),
        ([{"key": "a", "port": 5021}, {"key": "b", "port": 5021}], "重复"),
        ([{"key": "a", "port": 5015}], "占用"),      # playwright
        ([{"key": "a", "port": 80}], "超出范围"),
    ]
    for rows, needle in cases:
        messages = rag_kbs.validate(rows)
        assert any(needle in m for m in messages), (rows, messages)


def test_save_raises_on_invalid_rows(isolated):
    with pytest.raises(ValueError):
        rag_kbs.save_kbs([{"key": "bad key", "port": 5021}])
    assert not isolated.exists()   # 校验不过就不该落盘


def test_suggest_kb_picks_a_free_port(isolated):
    rag_kbs.save_kbs([{"key": "default", "port": 5014}, {"key": "a", "port": 5021}])
    assert rag_kbs.suggest_kb()["port"] == 5022
    # 传在编辑中的行时，以那些行为准（页面上刚删掉一行还没保存）
    assert rag_kbs.suggest_kb([{"key": "a", "port": 5021}])["port"] == 5022


def test_get_kb_and_describe_keys(isolated):
    rag_kbs.save_kbs([{"key": "default", "label": "默认知识库", "port": 5014},
                      {"key": "ruoyi", "label": "若依后台", "port": 5021}])
    assert rag_kbs.get_kb("").key == "default"     # 空 = 默认库
    assert rag_kbs.get_kb("ruoyi").label == "若依后台"
    assert rag_kbs.get_kb("没这个") is None
    assert "ruoyi（若依后台）" in rag_kbs.describe_keys()


def test_launcher_exposes_one_service_per_kb(isolated, monkeypatch):
    """启动器按注册表一库一条服务：名字不同、端口不同、WORKSPACE 不同。"""
    import importlib.util
    import sys

    root = rag_kbs.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("_launcher_kb_test", root / "launcher.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    try:
        spec.loader.exec_module(module)
        # launcher 自己 import 的是真的 rag_kbs 模块，所以这里换掉的是同一个对象
        plain = {(s.name, s.port) for s in module._default_services()}
        assert ("lightrag", 5014) in plain

        rag_kbs.save_kbs([{"key": "default", "label": "默认知识库", "port": 5014},
                          {"key": "ruoyi", "label": "若依后台", "port": 5021}])
        with_kb = {s.name: s for s in module._default_services()}
        assert set(with_kb) >= {"lightrag", "lightrag-ruoyi"}
        assert with_kb["lightrag-ruoyi"].port == 5021
        assert with_kb["lightrag-ruoyi"].env["WORKSPACE"] == "ruoyi"
        assert with_kb["lightrag"].env["WORKSPACE"] == ""
    finally:
        sys.modules.pop(spec.name, None)
