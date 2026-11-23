"""6일차 Random Forest와 부속 JSON을 서버 시작 시 한 번 불러옵니다.

- joblib.load()는 pickle을 실행하므로, 불러오기 전에 SHA256SUMS.txt와 해시를 비교해
  우리가 학습한 그 파일인지 확인합니다.
- Feature 수(1,140 = 30 Step × 38)와 Class 6개가 학습 정보와 일치하는지 확인합니다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

import joblib

MODEL_FILE = "rf_action_baseline.joblib"
FEATURE_COLUMNS_FILE = "rf_feature_columns.json"
TRAINING_INFO_FILE = "rf_training_info.json"
CHECKSUM_FILE = "SHA256SUMS.txt"

FRAME_FEATURE_COUNT = 38


class ModelLoadError(RuntimeError):
    pass


@dataclass
class ActionModelBundle:
    model: object
    feature_columns: list[str]
    classes: list[str]
    sequence_steps: int
    feature_count: int
    training_info: dict
    files: dict[str, str] = field(default_factory=dict)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_checksums(model_dir: Path) -> dict[str, str]:
    """SHA256SUMS.txt에 적힌 파일의 해시가 맞는지 확인합니다."""
    checksum_path = model_dir / CHECKSUM_FILE
    if not checksum_path.exists():
        raise ModelLoadError(f"{CHECKSUM_FILE}이 없습니다: {checksum_path}")

    verified = {}
    for line in checksum_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        expected, name = line.split(maxsplit=1)
        name = name.strip().lstrip("*")
        path = model_dir / name
        if not path.exists():
            raise ModelLoadError(f"모델 파일이 없습니다: {path}")
        actual = _sha256(path)
        if actual != expected:
            raise ModelLoadError(f"{name}의 해시가 다릅니다. 신뢰할 수 없는 파일이라 불러오지 않습니다.")
        verified[name] = actual[:12]
    return verified


def load_action_model(model_dir: Path) -> ActionModelBundle:
    model_dir = Path(model_dir)
    verified = verify_checksums(model_dir)

    feature_columns = json.loads((model_dir / FEATURE_COLUMNS_FILE).read_text(encoding="utf-8"))
    training_info = json.loads((model_dir / TRAINING_INFO_FILE).read_text(encoding="utf-8"))
    model = joblib.load(model_dir / MODEL_FILE)

    sequence_steps = int(training_info["sequence_steps"])
    feature_count = int(training_info["feature_count"])
    classes = [str(c) for c in model.classes_]

    if sequence_steps * FRAME_FEATURE_COUNT != feature_count:
        raise ModelLoadError(f"Step×Feature가 맞지 않습니다: {sequence_steps}×{FRAME_FEATURE_COUNT} != {feature_count}")
    if len(feature_columns) != feature_count:
        raise ModelLoadError(f"Feature 순서 파일 길이 {len(feature_columns)} != {feature_count}")
    if int(getattr(model, "n_features_in_", feature_count)) != feature_count:
        raise ModelLoadError(f"모델 입력 차원 {model.n_features_in_} != {feature_count}")
    if sorted(classes) != sorted(training_info["classes"]):
        raise ModelLoadError(f"모델 Class {classes}가 학습 정보 {training_info['classes']}와 다릅니다")
    names_in = getattr(model, "feature_names_in_", None)
    if names_in is not None and list(names_in) != feature_columns:
        raise ModelLoadError("모델의 Feature 이름 순서가 rf_feature_columns.json과 다릅니다")

    return ActionModelBundle(
        model=model,
        feature_columns=feature_columns,
        classes=classes,
        sequence_steps=sequence_steps,
        feature_count=feature_count,
        training_info=training_info,
        files=verified,
    )
