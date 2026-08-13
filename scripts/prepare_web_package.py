import shutil
from pathlib import Path


class WebPackagePreparationError(RuntimeError):
    pass


def prepare_web_package(repo_root: Path) -> Path:
    source = repo_root / "web" / "dist"
    if not (source / "index.html").is_file():
        raise WebPackagePreparationError(
            "WebUI 构建产物缺失，请先运行 npm run build。"
        )

    target = repo_root / "src" / "code_agent" / "web_dist"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target
