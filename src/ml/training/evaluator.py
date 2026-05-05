from typing import Optional

from src.observability.logging import get_logger

logger = get_logger(__name__)


class Evaluator:
    """Computes NDCG@10 for the re-ranker and F1 for the anomaly detector."""

    def ndcg_at_10(self, y_score: list[float], y_true: list[float]) -> Optional[float]:
        """Compute NDCG@10 using scikit-learn.

        Args:
            y_score: Predicted relevance scores (one score per item, batched as [[scores]] or flat).
            y_true:  Ground-truth relevance labels.

        Returns:
            NDCG@10 float in [0, 1] or None if input is invalid.
        """
        if not y_score or not y_true or len(y_score) != len(y_true):
            return None
        try:
            from sklearn.metrics import ndcg_score
            import numpy as np
            score = ndcg_score(
                np.array(y_true).reshape(1, -1),
                np.array(y_score).reshape(1, -1),
                k=10,
            )
            return float(round(score, 4))
        except Exception as exc:
            logger.warning("ndcg_evaluation_failed", error=str(exc))
            return None

    def f1_score(self, y_true: list[int], y_pred: list[int]) -> Optional[float]:
        """Compute binary F1 score using scikit-learn.

        Args:
            y_true: Ground-truth binary labels (0/1).
            y_pred: Predicted binary labels (0/1).

        Returns:
            F1 float in [0, 1] or None if input is invalid.
        """
        if not y_true or not y_pred or len(y_true) != len(y_pred):
            return None
        try:
            from sklearn.metrics import f1_score
            score = f1_score(y_true, y_pred, zero_division=0)
            return float(round(score, 4))
        except Exception as exc:
            logger.warning("f1_evaluation_failed", error=str(exc))
            return None
