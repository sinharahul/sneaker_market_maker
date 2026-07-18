"""Pickle-free IQL checkpoint persistence."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Literal

import torch
from safetensors.torch import load_file, save_file
from torch import Tensor


class CheckpointError(RuntimeError):
    pass


@dataclass(frozen=True)
class CheckpointManifest:
    architecture: Literal["distributional_iql_v1"]
    run_manifest_hash: str
    environment_hash: str
    step: int
    tensor_hash: str
    complete: bool

    def to_json(self) -> str:
        return json.dumps(asdict(self), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, value: str) -> CheckpointManifest:
        try:
            payload = json.loads(value)
            if not isinstance(payload, dict) or set(payload) != {
                "architecture",
                "run_manifest_hash",
                "environment_hash",
                "step",
                "tensor_hash",
                "complete",
            }:
                raise ValueError("manifest fields are invalid")
            if (
                not isinstance(payload["architecture"], str)
                or not isinstance(payload["run_manifest_hash"], str)
                or not isinstance(payload["environment_hash"], str)
                or not isinstance(payload["tensor_hash"], str)
                or not isinstance(payload["step"], int)
                or isinstance(payload["step"], bool)
                or payload["step"] < 0
                or not isinstance(payload["complete"], bool)
            ):
                raise ValueError("manifest values are invalid")
            return cls(**payload)
        except (json.JSONDecodeError, TypeError, ValueError) as error:
            raise CheckpointError("checkpoint manifest is invalid") from error


class CheckpointStore:
    def save(
        self,
        path: Path,
        manifest: CheckpointManifest,
        tensors: Mapping[str, Tensor],
    ) -> str:
        if manifest.architecture != "distributional_iql_v1":
            raise CheckpointError("architecture is not allowlisted")
        if not tensors:
            raise CheckpointError("checkpoint has no tensors")
        normalized: dict[str, Tensor] = {}
        for name in sorted(tensors):
            tensor = tensors[name]
            if not isinstance(name, str) or not name:
                raise CheckpointError("tensor names must be nonempty strings")
            if not isinstance(tensor, Tensor):
                raise TypeError("checkpoint values must be tensors")
            if not torch.isfinite(tensor).all():
                raise CheckpointError(f"tensor {name!r} is non-finite")
            normalized[name] = tensor.detach().cpu().contiguous()

        path.mkdir(parents=True, exist_ok=True)
        tensor_path = path / "weights.safetensors"
        tensor_temp = path / ".weights.safetensors.tmp"
        manifest_path = path / "manifest.json"
        manifest_temp = path / ".manifest.json.tmp"
        try:
            save_file(normalized, str(tensor_temp))
            tensor_hash = sha256(tensor_temp.read_bytes()).hexdigest()
            persisted = replace(manifest, tensor_hash=tensor_hash)
            manifest_temp.write_text(persisted.to_json())
            os.replace(tensor_temp, tensor_path)
            os.replace(manifest_temp, manifest_path)
        finally:
            tensor_temp.unlink(missing_ok=True)
            manifest_temp.unlink(missing_ok=True)
        return tensor_hash

    def load(
        self,
        path: Path,
        expected_run_manifest_hash: str,
        expected_environment_hash: str,
    ) -> tuple[CheckpointManifest, dict[str, Tensor]]:
        try:
            manifest = CheckpointManifest.from_json((path / "manifest.json").read_text())
        except OSError as error:
            raise CheckpointError("checkpoint manifest is unavailable") from error
        if not manifest.complete:
            raise CheckpointError("checkpoint is incomplete")
        if manifest.architecture != "distributional_iql_v1":
            raise CheckpointError("architecture is not allowlisted")
        if manifest.run_manifest_hash != expected_run_manifest_hash:
            raise CheckpointError("run manifest mismatch")
        if manifest.environment_hash != expected_environment_hash:
            raise CheckpointError("environment mismatch")
        tensor_path = path / "weights.safetensors"
        try:
            actual_hash = sha256(tensor_path.read_bytes()).hexdigest()
        except OSError as error:
            raise CheckpointError("checkpoint tensors are unavailable") from error
        if actual_hash != manifest.tensor_hash:
            raise CheckpointError("tensor hash mismatch")
        try:
            return manifest, load_file(tensor_path)
        except Exception as error:
            raise CheckpointError("checkpoint tensors are invalid") from error


__all__ = ["CheckpointError", "CheckpointManifest", "CheckpointStore"]
