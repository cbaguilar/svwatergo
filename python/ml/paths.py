from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MLPaths:
    root: Path

    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def processed(self) -> Path:
        return self.data / "processed"

    @property
    def features(self) -> Path:
        return self.data / "features"

    @property
    def derived(self) -> Path:
        return self.data / "derived"

    @property
    def manifests(self) -> Path:
        return self.data / "manifests"

    @property
    def checkpoints(self) -> Path:
        return self.data / "checkpoints"


def default_paths(repo_root: Path | None = None) -> MLPaths:
    if repo_root is None:
        repo_root = Path(__file__).resolve().parents[2]
    return MLPaths(root=repo_root)
