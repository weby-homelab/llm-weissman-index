from __future__ import annotations

import importlib.util
from pathlib import Path


def _load_inspector():
    script = Path(__file__).parents[1] / "scripts" / "inspect_artifacts.py"
    spec = importlib.util.spec_from_file_location("lwi_inspect_artifacts", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_artifact_paths_are_anchored_to_repository_not_cwd(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "dist").mkdir()
    monkeypatch.chdir(tmp_path)

    paths = _load_inspector().artifact_paths()

    repository_dist = Path(__file__).parents[1] / "dist"
    assert all(path.parent == repository_dist for path in paths)
