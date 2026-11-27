"""Import bans (DEV invariants 7 and the ablation rule): the checker must not share code with the solver,
and the product (pipeline, app) must never reach the LLM-writes-code ablation."""

import ast
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parents[1] / "src"

BANNED = {
    "nstrip/checker": {"z3", "nstrip.encode", "nstrip.solve"},
    "nstrip/pipeline.py": {"nstrip.ablation"},
    "nstrip/app": {"nstrip.ablation"},
}


def imported_modules(source: str, package: str) -> set[str]:
    """Absolute names of everything `source` imports, resolving relative imports against `package`."""
    mods: set[str] = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            mods |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            base = node.module or ""
            if node.level:
                parts = package.split(".")
                parts = parts[: len(parts) - (node.level - 1)]
                base = ".".join(parts + ([base] if base else []))
            mods.add(base)
            mods |= {f"{base}.{a.name}" for a in node.names}  # `from nstrip import encode`
    return mods


def is_banned(module: str, banned: set[str]) -> bool:
    return any(module == b or module.startswith(b + ".") for b in banned)


def test_detector_sees_relative_and_from_imports():
    assert is_banned_any("from ..encode import compile_problem", "nstrip.checker", {"nstrip.encode"})
    assert is_banned_any("from nstrip import solve", "nstrip.checker", {"nstrip.solve"})
    assert is_banned_any("import z3.z3util", "nstrip.checker", {"z3"})
    assert not is_banned_any("from nstrip.models.plan import Plan", "nstrip.checker", {"nstrip.encode"})


def is_banned_any(source: str, package: str, banned: set[str]) -> bool:
    return any(is_banned(m, banned) for m in imported_modules(source, package))


@pytest.mark.parametrize("target", sorted(BANNED))
def test_import_ban(target):
    path = SRC / target
    files = sorted(path.rglob("*.py")) if path.is_dir() else [path] if path.exists() else []
    if not files:
        pytest.skip(f"{target} not built yet")
    for f in files:
        package = ".".join(f.relative_to(SRC).with_suffix("").parts[:-1])
        bad = {m for m in imported_modules(f.read_text(), package) if is_banned(m, BANNED[target])}
        assert not bad, f"{f.relative_to(SRC)} imports {sorted(bad)}"
