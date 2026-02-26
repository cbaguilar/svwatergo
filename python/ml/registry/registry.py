from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

import yaml


@dataclass(frozen=True)
class DatasetRef:
    name: str
    manifest: str
    version: str | None = None
    feature_set: str | None = None
    notes: str | None = None


@dataclass(frozen=True)
class Registry:
    datasets: Dict[str, DatasetRef]

    def get(self, name: str) -> DatasetRef:
        if name not in self.datasets:
            raise KeyError(f"Dataset not found: {name}")
        return self.datasets[name]

    def list(self) -> List[DatasetRef]:
        return list(self.datasets.values())


def load_registry(path: Path) -> Registry:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    datasets = {}
    for name, item in (data.get("datasets") or {}).items():
        datasets[name] = DatasetRef(
            name=name,
            manifest=item.get("manifest"),
            version=item.get("version"),
            feature_set=item.get("feature_set"),
            notes=item.get("notes"),
        )
    return Registry(datasets=datasets)


def save_registry(path: Path, registry: Registry) -> None:
    out = {"datasets": {}}
    for name, ds in registry.datasets.items():
        out["datasets"][name] = {
            "manifest": ds.manifest,
            "version": ds.version,
            "feature_set": ds.feature_set,
            "notes": ds.notes,
        }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(out, sort_keys=True), encoding="utf-8")
