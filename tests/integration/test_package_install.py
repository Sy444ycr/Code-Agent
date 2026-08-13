from pathlib import Path

import pytest

from scripts.prepare_web_package import WebPackagePreparationError, prepare_web_package


def test_prepare_web_package_rejects_missing_frontend_dist(tmp_path: Path) -> None:
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    with pytest.raises(WebPackagePreparationError, match="WebUI 构建产物缺失"):
        prepare_web_package(tmp_path)


def test_prepare_web_package_copies_frontend_dist(tmp_path: Path) -> None:
    source = tmp_path / "web" / "dist"
    source.mkdir(parents=True)
    (source / "index.html").write_text("<main>WebUI</main>", encoding="utf-8")
    (source / "assets").mkdir()
    (source / "assets" / "app.js").write_text("console.log('WebUI')", encoding="utf-8")
    (tmp_path / "src" / "code_agent").mkdir(parents=True)

    target = prepare_web_package(tmp_path)

    assert target == tmp_path / "src" / "code_agent" / "web_dist"
    assert (target / "index.html").read_text(encoding="utf-8") == "<main>WebUI</main>"
    assert (target / "assets" / "app.js").read_text(encoding="utf-8") == "console.log('WebUI')"
