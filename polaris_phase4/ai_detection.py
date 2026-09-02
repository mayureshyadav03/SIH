"""
ai_detection.py
----------------
Phase 4 — Iceberg & Sea-Ice Detection
AI/ML detection-model component (SRD Section 3/7, Roadmap Phase 4).

This module provides a small, modular AI/ML detection component that
sits on top of the computer-vision segmentation performed in
image_processing.py. It is intentionally simple (per Roadmap Phase 4:
"Develop and evaluate an AI/ML detection model") — it is a pixel-level
unsupervised classifier (KMeans) that separates ice-like pixels from
non-ice pixels using intensity + local-texture features, wrapped in a
scikit-learn based model class so it can later be swapped for a trained
supervised model (e.g. CNN) without changing the rest of the pipeline.

This module does NOT perform iceberg trajectory prediction — that is
Phase 7, out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import cv2
from sklearn.cluster import KMeans


@dataclass
class DetectionResult:
    """Container for AI/ML detection output for a single image."""
    mask: np.ndarray          # binary mask, {0, 255}, ice-class pixels = 255
    ice_cluster_label: int    # which KMeans cluster was identified as "ice"
    model_confidence: float   # simple confidence score in [0, 1]


class IceDetectionModel:
    """
    Modular AI/ML ice/iceberg detection model.

    Uses unsupervised clustering (KMeans, n_clusters=2) over per-pixel
    feature vectors (intensity + local texture variance) to separate
    ice-like pixels from open-water/background pixels. The cluster with
    higher mean intensity is assumed to correspond to ice (ice/snow has
    high reflectance relative to open water in the visible/NIR MODIS bands).

    This class exposes a fit_predict interface so it can be replaced later
    with a supervised model (e.g. a trained CNN) without changing how
    detection.py calls it.
    """

    def __init__(self, n_clusters: int = 2, random_state: int = 42):
        self.n_clusters = n_clusters
        self.random_state = random_state
        self._model = None

    def _build_features(self, image: np.ndarray) -> np.ndarray:
        """
        Build a simple per-pixel feature vector: [intensity, local texture].
        Local texture is approximated via a local standard-deviation filter,
        which helps separate rough ice edges/floes from smooth open water.
        """
        image_f = image.astype(np.float32)

        mean = cv2.blur(image_f, (5, 5))
        sq_mean = cv2.blur(image_f * image_f, (5, 5))
        local_var = np.clip(sq_mean - mean * mean, 0, None)
        local_std = np.sqrt(local_var)

        features = np.stack([image_f.flatten(), local_std.flatten()], axis=1)
        return features

    def fit_predict(self, image: np.ndarray) -> DetectionResult:
        """
        Fit the clustering model on the given image and produce a
        binary ice/non-ice detection mask.

        Args:
            image: 8-bit 2D NumPy array (typically the CV-segmented or
                denoised image from image_processing.py).

        Returns:
            DetectionResult with binary mask, identified ice cluster label,
            and a simple confidence score.
        """
        if not isinstance(image, np.ndarray) or image.ndim != 2:
            raise ValueError("IceDetectionModel expects a 2D NumPy array.")
        if image.size == 0:
            raise ValueError("Input image to IceDetectionModel is empty.")

        features = self._build_features(image)

        self._model = KMeans(
            n_clusters=self.n_clusters,
            n_init=10,
            random_state=self.random_state,
        )
        labels = self._model.fit_predict(features)

        # Identify which cluster corresponds to "ice" by mean intensity.
        cluster_means = [
            features[labels == c, 0].mean() if np.any(labels == c) else -np.inf
            for c in range(self.n_clusters)
        ]
        ice_cluster = int(np.argmax(cluster_means))

        mask = (labels == ice_cluster).astype(np.uint8).reshape(image.shape) * 255

        # Simple confidence: how well-separated the two cluster means are,
        # normalized to [0, 1]. Larger separation -> higher confidence.
        intensity_range = features[:, 0].max() - features[:, 0].min()
        if intensity_range < 1e-6 or self.n_clusters < 2:
            confidence = 0.5
        else:
            sorted_means = sorted(cluster_means)
            separation = sorted_means[-1] - sorted_means[-2]
            confidence = float(np.clip(separation / intensity_range, 0.0, 1.0))

        return DetectionResult(
            mask=mask,
            ice_cluster_label=ice_cluster,
            model_confidence=confidence,
        )


def evaluate_detection(predicted_mask: np.ndarray, ground_truth_mask: np.ndarray) -> dict:
    """
    Basic detection evaluation mechanism.

    Compares a predicted binary mask against a ground-truth binary mask
    and reports standard detection-accuracy metrics. This is limited to
    detection accuracy evaluation only (no trajectory/risk metrics).

    Args:
        predicted_mask: Binary mask (0/255 or 0/1), model output.
        ground_truth_mask: Binary mask (0/255 or 0/1), reference/labeled data.

    Returns:
        Dict with keys: 'accuracy', 'iou', 'precision', 'recall', 'f1_score'.
    """
    if predicted_mask.shape != ground_truth_mask.shape:
        raise ValueError("Predicted mask and ground-truth mask must have the same shape.")

    pred = (predicted_mask > 0).astype(np.uint8)
    gt = (ground_truth_mask > 0).astype(np.uint8)

    tp = int(np.sum((pred == 1) & (gt == 1)))
    tn = int(np.sum((pred == 0) & (gt == 0)))
    fp = int(np.sum((pred == 1) & (gt == 0)))
    fn = int(np.sum((pred == 0) & (gt == 1)))

    total = tp + tn + fp + fn
    accuracy = (tp + tn) / total if total > 0 else 0.0

    union = tp + fp + fn
    iou = tp / union if union > 0 else 0.0

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1_score = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "accuracy": round(accuracy, 4),
        "iou": round(iou, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1_score, 4),
    }
