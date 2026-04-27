"""Per-project brand symlink wiring and placeholder helpers.

Private module — used by `matctl course/doc add`, `matctl course/doc modify`,
and `matctl link/unlink`.

Each project directory gets four symlinks:
  <project>/_brand.yml    → pkg/brands/<brand>/_brand.yml
  <project>/brand.scss    → pkg/brands/<brand>/brand.scss
  <project>/brand-assets/ → pkg/brands/<brand>/assets/
  <project>/shared/       → pkg/shared/
"""

from __future__ import annotations

import os
from pathlib import Path


_BRAND_SYMLINKS = ("_brand.yml", "brand.scss", "brand-assets", "shared")


def link_project(
    project_dir: Path,
    brand: str,
    pkg_root: Path,
    force: bool = False,
) -> None:
    """Create the four per-project symlinks inside project_dir."""
    brand_dir = pkg_root / "brands" / brand
    targets = {
        "_brand.yml": brand_dir / "_brand.yml",
        "brand.scss": brand_dir / "brand.scss",
        "brand-assets": brand_dir / "assets",
        "shared": pkg_root / "shared",
    }
    for link_name, src in targets.items():
        dst = project_dir / link_name
        broken = dst.is_symlink() and not dst.exists()
        if not broken and (dst.is_symlink() or dst.exists()):
            if not force:
                continue
            if dst.is_symlink() or dst.is_file():
                dst.unlink()
            else:
                import shutil
                shutil.rmtree(dst)
        elif broken:
            dst.unlink()
        dst.symlink_to(src)


def unlink_project(project_dir: Path) -> None:
    """Remove per-project symlinks that point into a brands/ or shared/ dir."""
    for link_name in _BRAND_SYMLINKS:
        dst = project_dir / link_name
        if not dst.is_symlink():
            continue
        try:
            target = Path(os.readlink(dst))
        except OSError:
            continue
        if "brands" in target.parts or target.name == "shared":
            dst.unlink()


def relink_project(project_dir: Path, new_brand: str, pkg_root: Path) -> None:
    """Switch an existing project to a new brand: unlink then link."""
    unlink_project(project_dir)
    link_project(project_dir, new_brand, pkg_root, force=True)


def brand_quarto_book_keys(brand: str) -> dict[str, str]:
    """Return {'favicon': path, 'logo': path} for non-generic brands; empty dict for generic."""
    if brand == "generic":
        return {}
    logo_files = {"thd": "THD-logo.png", "pf": "logo_pf.svg"}
    favicon_files = {"thd": "favicon.ico", "pf": "favicon.svg"}
    logo = logo_files.get(brand, f"logo_{brand}.png")
    favicon = favicon_files.get(brand, f"favicon_{brand}.png")
    return {
        "favicon": f"brand-assets/{favicon}",
        "logo": f"brand-assets/{logo}",
    }


def brand_placeholders(brand: str) -> dict[str, str]:
    """Return the YAML placeholder substitutions for a given brand."""
    if brand == "generic":
        return {
            "{{LOGO_LINE}}": "",
            "{{FAVICON_LINE}}": "",
        }
    logo_files = {
        "thd": "THD-logo.png",
        "pf": "logo_pf.svg",
    }
    favicon_files = {
        "thd": "favicon.ico",
        "pf": "favicon.svg",
    }
    logo = logo_files.get(brand, f"logo_{brand}.png")
    favicon = favicon_files.get(brand, f"favicon_{brand}.png")
    return {
        "{{LOGO_LINE}}": f"logo:   brand-assets/{logo}",
        "{{FAVICON_LINE}}": f"favicon:  brand-assets/{favicon}",
    }
