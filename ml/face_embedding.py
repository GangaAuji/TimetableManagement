"""Face detection + embedding generation using TFLite models.

This module is designed to be compatible with the APK model contract:
- Detector: yolov8n_float32.tflite
- Embedder: mobilefacenet.tflite
"""

# pyright: reportMissingImports=false

from __future__ import annotations

import os
import importlib
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np

def _load_interpreter_class():
    """Resolve a TFLite Interpreter class at runtime."""
    try:
        module = importlib.import_module("tflite_runtime.interpreter")
        return getattr(module, "Interpreter")
    except Exception:
        try:
            module = importlib.import_module("ai_edge_litert.interpreter")
            return getattr(module, "Interpreter")
        except Exception:
            try:
                module = importlib.import_module("tensorflow.lite")
                return getattr(module, "Interpreter")
            except Exception:
                return None


Interpreter = _load_interpreter_class()


@dataclass
class FaceEmbeddingResult:
    embedding: list[float]
    quality_score: Optional[float]
    embedding_version: str


class TFLiteFacePipeline:
    def __init__(
        self,
        detector_model_path: str,
        embedder_model_path: str,
        detector_conf_threshold: float = 0.35,
        detector_iou_threshold: float = 0.45,
    ):
        if Interpreter is None:
            raise RuntimeError(
                "No TFLite interpreter available. Install tflite-runtime or tensorflow."
            )

        if not os.path.exists(embedder_model_path):
            raise FileNotFoundError(f"MobileFaceNet model not found: {embedder_model_path}")

        self.detector_model_path = detector_model_path
        self.embedder_model_path = embedder_model_path
        self.detector_conf_threshold = float(detector_conf_threshold)
        self.detector_iou_threshold = float(detector_iou_threshold)

        self._detector = None
        if detector_model_path and os.path.exists(detector_model_path):
            self._detector = Interpreter(model_path=detector_model_path)
            self._detector.allocate_tensors()
            self._detector_in = self._detector.get_input_details()[0]
            self._detector_out = self._detector.get_output_details()[0]

        self._embedder = Interpreter(model_path=embedder_model_path)
        self._embedder.allocate_tensors()
        self._embedder_in = self._embedder.get_input_details()[0]
        self._embedder_out = self._embedder.get_output_details()[0]
        self._embed_input_h = int(self._embedder_in["shape"][1])
        self._embed_input_w = int(self._embedder_in["shape"][2])
        self._embed_output_dim = int(self._embedder_out["shape"][-1])

    def generate(self, image_bytes: bytes) -> FaceEmbeddingResult:
        image = self._decode_image(image_bytes)
        if image is None:
            raise ValueError("Invalid image payload")

        crop, det_score = self._extract_face_crop(image)
        embedding = self._embed_face(crop)

        return FaceEmbeddingResult(
            embedding=embedding,
            quality_score=det_score,
            embedding_version="mobilefacenet_192_l2_v1",
        )

    @staticmethod
    def _decode_image(image_bytes: bytes) -> Optional[np.ndarray]:
        if not image_bytes:
            return None
        arr = np.frombuffer(image_bytes, dtype=np.uint8)
        if arr.size == 0:
            return None
        return cv2.imdecode(arr, cv2.IMREAD_COLOR)

    def _extract_face_crop(self, image_bgr: np.ndarray) -> tuple[np.ndarray, Optional[float]]:
        if self._detector is None:
            return self._fallback_center_crop(image_bgr), None

        bbox, score = self._detect_face_yolov8(image_bgr)
        if bbox is None:
            return self._fallback_center_crop(image_bgr), None

        # Keep crop on the same oriented frame that detector saw.
        crop = self.crop_face_like_app(image_bgr, bbox)
        if crop.size == 0:
            return self._fallback_center_crop(image_bgr), None

        return crop, score

    def _detect_face_yolov8(self, image_bgr: np.ndarray) -> tuple[Optional[tuple[int, int, int, int]], Optional[float]]:
        in_h = int(self._detector_in["shape"][1])
        in_w = int(self._detector_in["shape"][2])

        resized, scale, pad_x, pad_y = self._letterbox(image_bgr, (in_w, in_h))
        img_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
        inp = np.expand_dims(img_rgb, axis=0)

        self._detector.set_tensor(self._detector_in["index"], inp.astype(self._detector_in["dtype"]))
        self._detector.invoke()
        raw = self._detector.get_tensor(self._detector_out["index"])

        boxes, scores = self._parse_yolov8_output(raw)
        if not boxes:
            return None, None

        kept = cv2.dnn.NMSBoxes(
            bboxes=boxes,
            scores=scores,
            score_threshold=self.detector_conf_threshold,
            nms_threshold=self.detector_iou_threshold,
        )
        if kept is None or len(kept) == 0:
            return None, None

        best_idx = int(kept[0][0] if isinstance(kept[0], (list, tuple, np.ndarray)) else kept[0])
        x, y, bw, bh = boxes[best_idx]

        bx = int((x - pad_x) / scale)
        by = int((y - pad_y) / scale)
        bw = int(bw / scale)
        bh = int(bh / scale)
        return (bx, by, bw, bh), float(scores[best_idx])

    @staticmethod
    def l2_normalize(vec: np.ndarray) -> np.ndarray:
        norm = float(np.linalg.norm(vec))
        return vec if norm == 0.0 else (vec / norm)

    @staticmethod
    def crop_face_like_app(image_bgr: np.ndarray, bbox: tuple[int, int, int, int]) -> np.ndarray:
        # bbox format matches app style: (left, top, width, height)
        x, y, w, h = bbox
        img_h, img_w = image_bgr.shape[:2]

        x = max(0, int(x))
        y = max(0, int(y))
        w = min(img_w - x, int(w))
        h = min(img_h - y, int(h))

        if w <= 0:
            w = 1
        if h <= 0:
            h = 1

        return image_bgr[y:y + h, x:x + w]

    def _parse_yolov8_output(self, raw_output: np.ndarray) -> tuple[list[list[int]], list[float]]:
        out = np.squeeze(raw_output)
        if out.ndim != 2:
            return [], []

        # Normalize layout to [N, C]. Common TFLite layout is [C, N].
        if out.shape[0] < out.shape[1]:
            out = out.T

        boxes: list[list[int]] = []
        scores: list[float] = []

        for pred in out:
            if pred.shape[0] < 5:
                continue

            cx, cy, w, h = float(pred[0]), float(pred[1]), float(pred[2]), float(pred[3])
            if w <= 0.0 or h <= 0.0:
                continue

            if pred.shape[0] >= 6:
                # Handle both [x,y,w,h,obj,cls...] and [x,y,w,h,cls...]
                obj = float(pred[4])
                cls_part = pred[5:]
                cls_score = float(np.max(cls_part)) if cls_part.size else 1.0
                score_a = obj * cls_score
                score_b = float(np.max(pred[4:]))
                conf = max(score_a, score_b)
            else:
                conf = float(pred[4])

            if conf < self.detector_conf_threshold:
                continue

            x = int(cx - (w / 2.0))
            y = int(cy - (h / 2.0))
            boxes.append([x, y, int(w), int(h)])
            scores.append(conf)

        return boxes, scores

    @staticmethod
    def _fallback_center_crop(image_bgr: np.ndarray) -> np.ndarray:
        h, w = image_bgr.shape[:2]
        side = int(min(h, w) * 0.8)
        side = max(side, 32)
        cx, cy = w // 2, h // 2
        x1 = max(0, cx - side // 2)
        y1 = max(0, cy - side // 2)
        x2 = min(w, x1 + side)
        y2 = min(h, y1 + side)
        crop = image_bgr[y1:y2, x1:x2]
        return crop if crop.size else image_bgr

    @staticmethod
    def _letterbox(image_bgr: np.ndarray, size: tuple[int, int]) -> tuple[np.ndarray, float, int, int]:
        target_w, target_h = size
        src_h, src_w = image_bgr.shape[:2]

        scale = min(target_w / src_w, target_h / src_h)
        new_w, new_h = int(src_w * scale), int(src_h * scale)

        resized = cv2.resize(image_bgr, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
        canvas = np.full((target_h, target_w, 3), 114, dtype=np.uint8)

        pad_x = (target_w - new_w) // 2
        pad_y = (target_h - new_h) // 2
        canvas[pad_y:pad_y + new_h, pad_x:pad_x + new_w] = resized
        return canvas, scale, pad_x, pad_y

    def _embed_face(self, face_bgr: np.ndarray) -> list[float]:
        # Match app preprocessing exactly.
        face = cv2.resize(face_bgr, (self._embed_input_w, self._embed_input_h), interpolation=cv2.INTER_LINEAR)
        rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB).astype(np.float32)
        rgb = (rgb - 127.5) / 127.5
        inp = np.expand_dims(rgb, axis=0).astype(np.float32)

        self._embedder.set_tensor(self._embedder_in["index"], inp)
        self._embedder.invoke()
        out = self._embedder.get_tensor(self._embedder_out["index"])
        emb = np.asarray(out[0], dtype=np.float32)

        if emb.shape[0] != self._embed_output_dim:
            raise ValueError(f"Expected {self._embed_output_dim}-d embedding, got {emb.shape[0]}")
        if self._embed_output_dim != 192:
            raise ValueError(f"MobileFaceNet output must be 192-d, got {self._embed_output_dim}")

        emb = self.l2_normalize(emb)
        norm = float(np.linalg.norm(emb))
        if norm <= 0.0:
            raise ValueError("Embedding norm is zero")
        if not (0.95 <= norm <= 1.05):
            raise ValueError(f"Embedding norm out of range after L2: {norm}")

        return emb.astype(np.float32).tolist()


_PIPELINE: Optional[TFLiteFacePipeline] = None


def get_face_pipeline(
    detector_model_path: str,
    embedder_model_path: str,
    detector_conf_threshold: float,
    detector_iou_threshold: float,
) -> TFLiteFacePipeline:
    global _PIPELINE
    if _PIPELINE is None:
        _PIPELINE = TFLiteFacePipeline(
            detector_model_path=detector_model_path,
            embedder_model_path=embedder_model_path,
            detector_conf_threshold=detector_conf_threshold,
            detector_iou_threshold=detector_iou_threshold,
        )
    return _PIPELINE
