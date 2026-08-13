import shutil
import sys
from pathlib import Path
from re import findall


class WebPackagePreparationError(RuntimeError):
    pass


ERROR_MESSAGE = (
    "WebUI \u6784\u5efa\u4ea7\u7269\u7f3a\u5931\uff0c\u8bf7\u5148\u8fd0\u884c npm run build\u3002"
)

TEXT_ASSET_SUFFIXES = {".css", ".html", ".js", ".mjs"}


def referenced_asset_paths(path: Path, source: Path) -> list[Path] | None:
    content = path.read_text(encoding="utf-8")
    references = [
        *findall(r'(?:src|href)\s*=\s*["\']([^"\']+)["\']', content),
        *findall(r'(?:import|export)\s*(?:[^"\']*?\s+from\s*)?["\']([^"\']+)["\']', content),
        *findall(r'url\(\s*["\']?([^"\')\s]+)', content),
    ]
    paths: list[Path] = []
    for reference in references:
        reference = reference.split("?", maxsplit=1)[0].split("#", maxsplit=1)[0]
        if not reference or reference.startswith(("data:", "http:", "https:", "//")):
            continue
        if not reference.startswith(("./", "../", "/assets/")):
            continue
        candidate = (
            source / reference.lstrip("/")
            if reference.startswith("/")
            else path.parent / reference
        ).resolve()
        try:
            candidate.relative_to(source.resolve())
        except ValueError:
            return None
        paths.append(candidate)
    return paths


def has_all_referenced_assets(source: Path) -> bool:
    for path in source.rglob("*"):
        if not path.is_file() or path.suffix not in TEXT_ASSET_SUFFIXES:
            continue
        references = referenced_asset_paths(path, source)
        if references is None or not all(reference.is_file() for reference in references):
            return False
    return True


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
        sys.stderr.buffer.write(f"{error}\n".encode())
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
