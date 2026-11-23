"""재학습 없이 추론 방식만 바꿔 보는 실험 (S02로 고르고 S03은 마지막 확인에만 사용).

사용: ai_service 폴더에서
  python -m scripts.experiment_inference <영상폴더> [--out 결과.json]

비교하는 방식
- base      : 지금 서비스 방식 (전체 구간 30 Step + 2초 Window 평균을 반씩)
- flip      : base + 좌우 반전한 관절로 한 번 더 예측해 확률 평균 (TTA)
- multi     : Window 길이를 1.5·2·3초 세 가지로 예측해 평균
- flip+multi: 두 가지를 함께
- fps25     : 30fps 등 다른 fps 영상을 학습 영상과 같은 25fps 간격으로 줄여서 예측
              (5일차 영상은 이미 25fps라 그대로이고, 30fps로 늘린 영상으로 영향만 확인)

같은 영상의 Pose 추출 결과를 한 번만 만들고 재사용합니다 (YOLO 결과는 방식과 무관).
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from services.model_loader import load_action_model
from services.pose_pipeline import PosePipeline, interpolate_low_confidence
from settings import load_settings
from src.feature_utils import LEFT_RIGHT_PAIRS
from src.multi_person_utils import feature_from_keypoints
from src.sequence_utils import flatten_sequence, resample_sequence

ACTION_IDS = {
    "A001": "bend_return", "A002": "leg_raise_lower", "A003": "walk_turn_walk",
    "A004": "drink_return", "A005": "sit_stand", "A006": "wave",
}


def mirror(points: np.ndarray, width: int) -> np.ndarray:
    """픽셀 좌표 (17, 2)를 좌우 반전하고 왼쪽·오른쪽 관절 번호를 바꿉니다."""
    out = points.copy()
    out[:, 0] = width - out[:, 0]
    for left, right in LEFT_RIGHT_PAIRS:
        out[[left, right]] = out[[right, left]]
    return out


def features(keypoints: np.ndarray, frame_ids: np.ndarray, flip: bool, width: int):
    rows, ids = [], []
    for fid, pts in zip(frame_ids, keypoints):
        f = feature_from_keypoints(mirror(pts, width) if flip else pts)
        if f is not None:
            rows.append(f)
            ids.append(fid)
    return np.asarray(rows, dtype=np.float32), np.asarray(ids, dtype=np.float32)


def windows(frame_ids: np.ndarray, fps: float, seconds: float, stride: float, min_frames: int):
    span = (frame_ids[-1] - frame_ids[0]) / fps
    if span <= seconds * 1.25:
        return [(0, len(frame_ids))]
    w, s = seconds * fps, max(stride * fps, 1.0)
    out, start = [], float(frame_ids[0])
    while start + w <= frame_ids[-1] + s:
        idx = np.where((frame_ids >= start) & (frame_ids < start + w))[0]
        if len(idx) >= min_frames:
            out.append((int(idx[0]), int(idx[-1]) + 1))
        start += s
    return out or [(0, len(frame_ids))]


def predict(bundle, feats, ids, fps, window_list, stride, min_frames):
    flat = lambda a, b: flatten_sequence(resample_sequence(feats[a:b], ids[a:b], bundle.sequence_steps))  # noqa: E731
    whole = bundle.model.predict_proba(flat(0, len(ids))[None])[0]
    window_means = []
    for seconds in window_list:
        rows = [flat(a, b) for a, b in windows(ids, fps, seconds, stride, min_frames)]
        window_means.append(bundle.model.predict_proba(np.stack(rows)).mean(axis=0))
    return 0.5 * whole + 0.5 * np.mean(window_means, axis=0)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_dir", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    s = load_settings()
    bundle = load_action_model(s.model_dir)
    pose = PosePipeline(s.model_dir / s.pose_model, s.image_size, s.person_confidence, s.tracker)
    classes = list(bundle.classes)
    stride, min_frames = s.window_stride_seconds, s.min_valid_frames

    variants = {
        "base": dict(flip=False, windows=[s.window_seconds]),
        "flip": dict(flip=True, windows=[s.window_seconds]),
        "multi": dict(flip=False, windows=[1.5, 2.0, 3.0]),
        "flip+multi": dict(flip=True, windows=[1.5, 2.0, 3.0]),
    }
    rows = []
    for path in sorted(args.video_dir.glob("S0*_A00*_T*.mp4")):
        subject, action_id = path.stem.split("_")[:2]
        expected = ACTION_IDS[action_id]
        tracks, fps, _, width, _ = pose.track_video(path)
        # 평가와 같은 기준으로 주인공 1명: Frame 수 × 평균 박스 Confidence가 가장 큰 사람
        track = max(tracks.values(), key=lambda t: len(t.frame_ids) * float(np.mean(t.box_conf)))
        frame_ids = np.asarray(track.frame_ids, dtype=np.float32)
        kps, _ = interpolate_low_confidence(np.stack(track.keypoints), np.stack(track.keypoint_conf),
                                            frame_ids, s.keypoint_min_confidence)

        # 30fps 영상처럼 만들기: 25fps 시간축 위에서 관절 좌표를 선형 보간
        t30 = np.arange(frame_ids[0] / fps, frame_ids[-1] / fps, 1 / 30.0)
        kps30 = np.stack([[np.interp(t30, frame_ids / fps, kps[:, j, a]) for a in range(2)] for j in range(17)]).transpose(2, 0, 1)

        row = {"file": path.name, "subject": subject, "expected": expected}
        for name, v in variants.items():
            feats, ids = features(kps, frame_ids, False, width)
            p = predict(bundle, feats, ids, fps, v["windows"], stride, min_frames)
            if v["flip"]:
                f2, i2 = features(kps, frame_ids, True, width)
                p = 0.5 * p + 0.5 * predict(bundle, f2, i2, fps, v["windows"], stride, min_frames)
            row[name] = {c: round(float(x), 4) for c, x in zip(classes, p)}
        # 30fps로 바꾼 영상: 그대로 넣기 vs 25fps 간격으로 되돌려 넣기
        f30, i30 = features(kps30, np.arange(len(t30), dtype=np.float32), False, width)
        row["as30fps"] = {c: round(float(x), 4) for c, x in zip(classes, predict(bundle, f30, i30, 30.0, [s.window_seconds], stride, min_frames))}
        rows.append(row)
        print(path.name, "done")

    names = list(variants) + ["as30fps"]
    for subject in sorted({r["subject"] for r in rows}):
        sub = [r for r in rows if r["subject"] == subject]
        print(f"\n[{subject}] 방식별 결과 (Top-1 / 정답 확률 평균 / 정답 순위 평균 / 확정(≥{s.confidence_threshold}, 차이≥{s.margin_threshold}) 중 정답)")
        for name in names:
            top1 = probs_true = rank = 0
            decided = decided_ok = 0
            for r in sub:
                p = r[name]
                order = sorted(p, key=p.get, reverse=True)
                top1 += order[0] == r["expected"]
                probs_true += p[r["expected"]]
                rank += order.index(r["expected"]) + 1
                conf, margin = p[order[0]], p[order[0]] - p[order[1]]
                if conf >= s.confidence_threshold and margin >= s.margin_threshold:
                    decided += 1
                    decided_ok += order[0] == r["expected"]
            n = len(sub)
            print(f"  {name:11s} Top-1 {top1}/{n}  정답확률 {probs_true / n:.3f}  순위 {rank / n:.2f}  확정 {decided_ok}/{decided}")
        for r in sub:
            line = "  ".join(f"{name}={max(r[name], key=r[name].get)[:8]}" for name in names)
            print(f"  {r['file']:18s} 정답={r['expected'][:8]:8s} {line}")
    if args.out:
        args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
