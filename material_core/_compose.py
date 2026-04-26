"""Template composer for the universal project scaffolder.

Orchestrates copying the _base overlay, a structure-specific overlay, an
optional slides overlay, assembling _quarto.yml from YAML fragments, and
running placeholder substitution. No click dependency — pure I/O.
"""

from __future__ import annotations

import shutil
from importlib.resources import as_file, files
from pathlib import Path

from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

from ._brand_resolve import brand_placeholders, brand_quarto_book_keys, link_project
from ._projects import available_brands
from ._scaffold import substitute_placeholders


def _yaml() -> YAML:
    y = YAML(typ="rt")
    y.preserve_quotes = True
    y.indent(mapping=2, sequence=4, offset=2)
    return y


def _load_fragment(path: Path) -> CommentedMap:
    with path.open("r", encoding="utf-8") as f:
        doc = _yaml().load(f)
    return doc if doc is not None else CommentedMap()


def _deep_merge(base: CommentedMap, overlay: CommentedMap) -> CommentedMap:
    """Merge overlay into base: scalars from overlay win, lists extend, dicts recurse."""
    result = CommentedMap()
    for key in base:
        result[key] = base[key]
    for key in overlay:
        if key in result:
            b_val = result[key]
            o_val = overlay[key]
            if isinstance(b_val, CommentedMap) and isinstance(o_val, CommentedMap):
                result[key] = _deep_merge(b_val, o_val)
            elif isinstance(b_val, list) and isinstance(o_val, list):
                result[key] = b_val + o_val
            else:
                result[key] = o_val
        else:
            result[key] = overlay[key]
    return result


def _overlay_copy(src: Path, dest: Path, skip: set[str] | None = None) -> None:
    skip = skip or set()
    shutil.copytree(
        src,
        dest,
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(*skip) if skip else None,
    )


def _templates_root() -> Path:
    ref = files("material_core") / "templates"
    # as_file context is not needed for directory traversal when installed editable
    return Path(str(ref))


def compose(
    dest: Path,
    *,
    structure: str,
    slides: bool,
    brand: str,
    placeholders: dict[str, str],
    pkg_root: Path,
) -> None:
    """Scaffold a project directory from orthogonal template fragments.

    Args:
        dest:         Target project directory (must not exist yet).
        structure:    "chapters" or "single".
        slides:       Whether to include the slides overlay.
        brand:        Brand id (validated by caller).
        placeholders: Project-level token substitutions ({{PROJECT_NAME}}, etc.).
        pkg_root:     material_core package root (for brand symlinks).
    """
    valid_structures = {"chapters", "single"}
    if structure not in valid_structures:
        raise ValueError(f"unknown structure {structure!r}; choose one of {sorted(valid_structures)}")

    valid_brands = available_brands(pkg_root)
    if brand not in valid_brands:
        raise ValueError(f"unknown brand {brand!r}; choose one of {valid_brands}")

    tmpl = _templates_root()

    # Step 1: Copy _base/ into dest/
    with as_file(files("material_core") / "templates" / "_base") as base_src:
        _overlay_copy(base_src, dest)

    # Step 2: Overlay structure/<structure>/ skipping the fragment YAML
    with as_file(files("material_core") / "templates" / "structure" / structure) as struct_src:
        _overlay_copy(struct_src, dest, skip={"_quarto.fragment.yml"})

    # Step 3: If slides, overlay slides/ → dest/slides/
    if slides:
        slides_dest = dest / "slides"
        slides_dest.mkdir(exist_ok=True)
        with as_file(files("material_core") / "templates" / "slides") as slides_src:
            _overlay_copy(slides_src, slides_dest)

    # Step 4: Assemble dest/_quarto.yml from fragments
    with as_file(files("material_core") / "templates" / "_quarto.common.fragment.yml") as common_path:
        common = _load_fragment(common_path)
    with as_file(files("material_core") / "templates" / "structure" / structure / "_quarto.fragment.yml") as struct_path:
        struct_frag = _load_fragment(struct_path)

    quarto_doc = _deep_merge(common, struct_frag)

    # Inject brand-specific book keys (favicon, sidebar.logo) for non-generic brands
    book_keys = brand_quarto_book_keys(brand)
    if book_keys and "book" in quarto_doc:
        quarto_doc["book"]["favicon"] = book_keys["favicon"]
        if "sidebar" not in quarto_doc["book"]:
            quarto_doc["book"]["sidebar"] = CommentedMap()
        quarto_doc["book"]["sidebar"]["logo"] = book_keys["logo"]

    quarto_path = dest / "_quarto.yml"
    with quarto_path.open("w", encoding="utf-8") as f:
        _yaml().dump(quarto_doc, f)

    # Step 5: Substitute all placeholders (project-level + brand tokens for slides)
    full_placeholders = {**placeholders, **brand_placeholders(brand)}
    substitute_placeholders(dest, full_placeholders)

    # Step 6: Wire per-project brand symlinks
    link_project(dest, brand, pkg_root)
