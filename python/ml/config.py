from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .paths import MLPaths, default_paths


@dataclass(frozen=True)
class RuntimeConfig:
    repo_root: Path
    registry_path: Path
    device: str | None = None

    @property
    def paths(self) -> MLPaths:
        return MLPaths(self.repo_root)


def default_config(repo_root: Path | None = None) -> RuntimeConfig:
    paths = default_paths(repo_root)
    registry_path = paths.root / "python" / "ml" / "registry" / "datasets.yaml"
    return RuntimeConfig(repo_root=paths.root, registry_path=registry_path, device=None)
