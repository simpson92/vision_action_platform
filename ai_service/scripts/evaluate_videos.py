"""5일차 영상(S02 검증, S03 테스트)으로 추론 정확도와 확률 분포를 확인합니다.

사용: ai_service 폴더에서
  python -m scripts.evaluate_videos <영상폴더> [--no-interp]
파일명 SXX_A00Y_T01.mp4의 A00Y로 정답을 알 수 있습니다.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from services.action_inference import InferenceOptions, predict_video
from services.model_loader import load_action_model
from services.pose_pipeline import PosePipeline
from settings import load_settings

ACTION_IDS = {
    "A001": "bend_return", "A002": "leg_raise_lower", "A003": "walk_turn_walk",
    "A004": "drink_return", "A005": "sit_stand", "A006": "wave",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("video_dir", type=Path)
    parser.add_argument("--no-interp", action="store_true")
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()

    s = load_settings()
    bundle = load_action_model(s.model_dir)
    pose = PosePipeline(s.model_dir / s.pose_model, s.image_size, s.person_confidence, s.tracker)
    options = InferenceOptions(s.min_valid_frames, s.confidence_threshold, s.margin_threshold,
                               s.window_seconds, s.window_stride_seconds)

    rows = []
    for path in sorted(args.video_dir.glob("S0*_A00*_T*.mp4")):
        subject, action_id = path.stem.split("_")[:2]
        result = pose.extract(path, not args.no_interp, s.keypoint_min_confidence)
        preds = predict_video(bundle, result, options)
        conf_by_id = {p.track_id: p.mean_box_conf for p in result.people}
        main_pred = max(preds, key=lambda p: p["valid_frames"] * conf_by_id[p["track_id"]]) if preds else None
        row = {
            "file": path.name, "subject": subject, "expected": ACTION_IDS[action_id],
            "raw_label": main_pred["raw_label"] if main_pred else None,
            "action_label": main_pred["action_label"] if main_pred else None,
            "confidence": main_pred["confidence"] if main_pred else 0,
            "margin": main_pred["margin"] if main_pred else 0,
            "people": len(preds),
            "probabilities": main_pred["probabilities"] if main_pred else {},
        }
        row["correct"] = row["raw_label"] == row["expected"]
        rows.append(row)
        print(f"{path.name:20s} 정답={row['expected']:16s} 1등={str(row['raw_label']):16s} "
              f"conf={row['confidence']:.3f} margin={row['margin']:.3f} {'O' if row['correct'] else 'X'} → {row['action_label']}")

    for subject in sorted({r["subject"] for r in rows}):
        sub = [r for r in rows if r["subject"] == subject]
        print(f"{subject}: Top-1 정확도 {sum(r['correct'] for r in sub)}/{len(sub)}")
    if args.out:
        args.out.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
