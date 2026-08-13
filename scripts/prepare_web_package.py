import shutil
import sys
from pathlib import Path
from re import findall


class WebPackagePreparationError(RuntimeError):
    pass


ERROR_MESSAGE = "WebUI 构建产物缺失，请先运行 npm run build。"


def has_all_referenced_assets(source: Path) -> bool:
    index_html = (source / "index.html").read_text(encoding="utf-8")
    asset_paths = findall(r'(?:src|href)=["\'](/assets/[^"\']+)["\']', index_html)
    return all((source / asset_path.lstrip("/")).is_file() for asset_path in asset_paths)


def prepare_web_package(repo_root: Path) -> Path:
    source = repo_root / "web" / "dist"
    if not (source / "index.html").is_file() or not has_all_referenced_assets(source):
        raise WebPackagePreparationError(ERROR_MESSAGE)

    target = repo_root / "src" / "code_agent" / "web_dist"
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(source, target)
    return target


def main() -> int:
    try:
        prepare_web_package(Path(__file__).resolve().parents[1])
    except WebPackagePreparationError as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
