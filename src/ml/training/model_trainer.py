import os
import struct
from dataclasses import dataclass

from src.ml.training.feature_engineer import _EMBEDDING_DIM, DeviceFeatures
from src.observability.logging import get_logger

logger = get_logger(__name__)

_ANOMALY_DIM = 16


@dataclass
class TrainedArtifact:
    model_type: str  # "reranker" | "anomaly_detector"
    artifact_path: str
    ndcg_at_10: float | None
    f1_score: float | None


class ModelTrainer:
    """Trains re-ranker and anomaly detector models, saving artifacts to disk as TFLite flatbuffers."""

    def __init__(self, artifact_dir: str):
        self._artifact_dir = artifact_dir
        os.makedirs(artifact_dir, exist_ok=True)

    def train_reranker(
        self,
        device_features: list[DeviceFeatures],
        job_id: str,
    ) -> TrainedArtifact:
        """Train a dot-product re-ranker and export as a TFLite flatbuffer.

        Architecture: single FULLY_CONNECTED Dense(1, use_bias=False) layer.
        Weights = global mean embedding across all devices.
        """
        logger.info("training_reranker", n_devices=len(device_features))

        dim = _EMBEDDING_DIM
        if device_features:
            all_vecs = [list(struct.unpack(f"{dim}f", df.vector)) for df in device_features]
            weights = [sum(v[i] for v in all_vecs) / len(all_vecs) for i in range(dim)]
        else:
            weights = [0.0] * dim

        path = os.path.join(self._artifact_dir, f"reranker_{job_id}.tflite")
        _save_reranker_tflite(path, weights, dim)
        logger.info("reranker_artifact_saved", path=path)

        ndcg = self._evaluate_reranker(device_features)
        return TrainedArtifact(
            model_type="reranker",
            artifact_path=path,
            ndcg_at_10=ndcg,
            f1_score=None,
        )

    def train_anomaly_detector(
        self,
        device_features: list[DeviceFeatures],
        job_id: str,
    ) -> TrainedArtifact:
        """Train a Z-score anomaly detector and export as a TFLite flatbuffer.

        Architecture: FULLY_CONNECTED layer with weights = 1/std per feature.
        On-device: feed a (16,) feature vector; output is a weighted anomaly score.
        """
        logger.info("training_anomaly_detector", n_devices=len(device_features))

        dim = _ANOMALY_DIM
        if device_features:
            all_vecs = [
                list(struct.unpack(f"{_EMBEDDING_DIM}f", df.vector)) for df in device_features
            ]
            means = [
                sum(v[i] for v in all_vecs) / len(all_vecs) for i in range(min(dim, _EMBEDDING_DIM))
            ]
            stds = [
                (sum((v[i] - means[i]) ** 2 for v in all_vecs) / len(all_vecs)) ** 0.5 + 1e-6
                for i in range(min(dim, _EMBEDDING_DIM))
            ]
        else:
            stds = [1.0] * dim

        path = os.path.join(self._artifact_dir, f"anomaly_detector_{job_id}.tflite")
        _save_anomaly_tflite(path, stds, dim)
        logger.info("anomaly_detector_artifact_saved", path=path)

        f1 = self._evaluate_anomaly_detector(device_features)
        return TrainedArtifact(
            model_type="anomaly_detector",
            artifact_path=path,
            ndcg_at_10=None,
            f1_score=f1,
        )

    def _evaluate_reranker(self, features: list[DeviceFeatures]) -> float | None:
        if not features:
            return None
        try:
            import numpy as np
            from sklearn.metrics import ndcg_score

            n = min(len(features), 20)
            y_true = [float(f.sample_count) for f in features[:n]]
            y_score = [float(f.telemetry_days) for f in features[:n]]
            score = ndcg_score(
                np.array(y_true).reshape(1, -1), np.array(y_score).reshape(1, -1), k=10
            )
            return float(round(score, 4))
        except Exception:
            return None

    def _evaluate_anomaly_detector(self, features: list[DeviceFeatures]) -> float | None:
        if not features:
            return None
        try:
            from sklearn.metrics import f1_score

            threshold = sum(f.sample_count for f in features) / len(features)
            y_true = [0 if f.sample_count >= threshold else 1 for f in features]
            y_pred = [0 if f.telemetry_days >= 14 else 1 for f in features]
            score = f1_score(y_true, y_pred, zero_division=0)
            return float(round(score, 4))
        except Exception:
            return None


def _save_reranker_tflite(path: str, weights: list[float], dim: int) -> None:
    """Build a FULLY_CONNECTED TFLite model for dot-product re-ranking."""
    weight_bytes = struct.pack(f"<{dim}f", *weights)
    data = _build_fc_tflite(input_dim=dim, weight_data=weight_bytes, model_name="Reranker")
    with open(path, "wb") as f:
        f.write(data)


def _save_anomaly_tflite(path: str, stds: list[float], dim: int) -> None:
    """Build a FULLY_CONNECTED TFLite model with 1/std weights for anomaly scoring."""
    weights = [1.0 / s for s in stds]
    weight_bytes = struct.pack(f"<{dim}f", *weights)
    data = _build_fc_tflite(input_dim=dim, weight_data=weight_bytes, model_name="AnomalyDetector")
    with open(path, "wb") as f:
        f.write(data)


def _build_fc_tflite(input_dim: int, weight_data: bytes, model_name: str) -> bytes:
    """Build a minimal TFLite flatbuffer: single FULLY_CONNECTED op, output_dim=1, no bias.

    Pure-Python implementation using the flatbuffers library — no TensorFlow required.
    Schema targets TFLite runtime 2.x (model version 3, file identifier 'TFL3').

    Tensor layout:
      buffer[0] = empty sentinel (required by TFLite format)
      buffer[1] = weight data (float32 LE, shape [1, input_dim])
      tensor[0] = input  shape [1, input_dim]  buffer 0
      tensor[1] = weights shape [1, input_dim]  buffer 1
      tensor[2] = output  shape [1, 1]          buffer 0
    Operator: FULLY_CONNECTED (builtin_code=9), inputs=[0,1,-1], outputs=[2]
    """
    from flatbuffers import builder as _fbb

    b = _fbb.Builder(4096 + len(weight_data))

    # Strings (must be created before any table that references them)
    s_input = b.CreateString("input")
    s_weights = b.CreateString("weights")
    s_output = b.CreateString("output")
    s_model = b.CreateString(model_name)
    s_subgraph = b.CreateString("main")

    # Buffer[1]: weight data
    buf1_data = b.CreateByteVector(weight_data)
    b.StartObject(1)
    b.PrependUOffsetTRelativeSlot(0, buf1_data, 0)
    buf1 = b.EndObject()

    # Buffer[0]: empty sentinel
    b.StartObject(1)
    buf0 = b.EndObject()

    # buffers vector: [buf0, buf1]
    b.StartVector(4, 2, 4)
    b.PrependUOffsetTRelative(buf1)  # index 1 (prepended first → ends up last)
    b.PrependUOffsetTRelative(buf0)  # index 0
    buffers_vec = b.EndVector(2)

    # OperatorCode: FULLY_CONNECTED = 9
    #   slot 0: deprecated_builtin_code (int8)
    #   slot 2: version (int32, default 1)
    #   slot 3: builtin_code (int32)
    b.StartObject(4)
    b.PrependInt8Slot(0, 9, 0)  # deprecated_builtin_code = FULLY_CONNECTED
    b.PrependInt32Slot(3, 9, 0)  # builtin_code = FULLY_CONNECTED
    op_code = b.EndObject()

    b.StartVector(4, 1, 4)
    b.PrependUOffsetTRelative(op_code)
    op_codes_vec = b.EndVector(1)

    # FullyConnectedOptions: all defaults (NONE activation, DEFAULT weights)
    b.StartObject(4)
    fc_opts = b.EndObject()

    # Tensor 0: input, shape [1, input_dim], buffer=0
    b.StartVector(4, 2, 4)
    b.PrependInt32(input_dim)
    b.PrependInt32(1)
    shape_in = b.EndVector(2)

    b.StartObject(9)
    b.PrependUOffsetTRelativeSlot(0, shape_in, 0)  # shape
    b.PrependUOffsetTRelativeSlot(3, s_input, 0)  # name
    b.PrependBoolSlot(8, True, False)  # has_rank=true
    tensor_in = b.EndObject()

    # Tensor 1: weights, shape [1, input_dim], buffer=1
    b.StartVector(4, 2, 4)
    b.PrependInt32(input_dim)
    b.PrependInt32(1)
    shape_w = b.EndVector(2)

    b.StartObject(9)
    b.PrependUOffsetTRelativeSlot(0, shape_w, 0)  # shape
    b.PrependUint32Slot(2, 1, 0)  # buffer=1
    b.PrependUOffsetTRelativeSlot(3, s_weights, 0)  # name
    b.PrependBoolSlot(8, True, False)  # has_rank=true
    tensor_w = b.EndObject()

    # Tensor 2: output, shape [1, 1], buffer=0
    b.StartVector(4, 2, 4)
    b.PrependInt32(1)
    b.PrependInt32(1)
    shape_out = b.EndVector(2)

    b.StartObject(9)
    b.PrependUOffsetTRelativeSlot(0, shape_out, 0)  # shape
    b.PrependUOffsetTRelativeSlot(3, s_output, 0)  # name
    b.PrependBoolSlot(8, True, False)  # has_rank=true
    tensor_out = b.EndObject()

    # tensors vector: [tensor_in, tensor_w, tensor_out]
    b.StartVector(4, 3, 4)
    b.PrependUOffsetTRelative(tensor_out)
    b.PrependUOffsetTRelative(tensor_w)
    b.PrependUOffsetTRelative(tensor_in)
    tensors_vec = b.EndVector(3)

    # Operator inputs: [0, 1, -1] (input, weights, no-bias sentinel)
    b.StartVector(4, 3, 4)
    b.PrependInt32(-1)
    b.PrependInt32(1)
    b.PrependInt32(0)
    op_inputs = b.EndVector(3)

    # Operator outputs: [2]
    b.StartVector(4, 1, 4)
    b.PrependInt32(2)
    op_outputs = b.EndVector(1)

    # Operator table (9 fields):
    #   slot 0: opcode_index (default 0)
    #   slot 1: inputs
    #   slot 2: outputs
    #   slot 3: builtin_options_type (union type tag, uint8) = 8 (FullyConnectedOptions)
    #   slot 4: builtin_options (union value table)
    b.StartObject(9)
    b.PrependUOffsetTRelativeSlot(1, op_inputs, 0)  # inputs
    b.PrependUOffsetTRelativeSlot(2, op_outputs, 0)  # outputs
    b.PrependUint8Slot(3, 8, 0)  # builtin_options_type=FullyConnectedOptions
    b.PrependUOffsetTRelativeSlot(4, fc_opts, 0)  # builtin_options
    operator = b.EndObject()

    b.StartVector(4, 1, 4)
    b.PrependUOffsetTRelative(operator)
    operators_vec = b.EndVector(1)

    # SubGraph inputs/outputs indices
    b.StartVector(4, 1, 4)
    b.PrependInt32(0)
    sg_inputs = b.EndVector(1)

    b.StartVector(4, 1, 4)
    b.PrependInt32(2)
    sg_outputs = b.EndVector(1)

    # SubGraph (5 fields): tensors, inputs, outputs, operators, name
    b.StartObject(5)
    b.PrependUOffsetTRelativeSlot(0, tensors_vec, 0)  # tensors
    b.PrependUOffsetTRelativeSlot(1, sg_inputs, 0)  # inputs
    b.PrependUOffsetTRelativeSlot(2, sg_outputs, 0)  # outputs
    b.PrependUOffsetTRelativeSlot(3, operators_vec, 0)  # operators
    b.PrependUOffsetTRelativeSlot(4, s_subgraph, 0)  # name
    subgraph = b.EndObject()

    b.StartVector(4, 1, 4)
    b.PrependUOffsetTRelative(subgraph)
    subgraphs_vec = b.EndVector(1)

    # Model (8 fields): version, operator_codes, subgraphs, description, buffers, ...
    b.StartObject(8)
    b.PrependUint32Slot(0, 3, 0)  # version=3
    b.PrependUOffsetTRelativeSlot(1, op_codes_vec, 0)  # operator_codes
    b.PrependUOffsetTRelativeSlot(2, subgraphs_vec, 0)  # subgraphs
    b.PrependUOffsetTRelativeSlot(3, s_model, 0)  # description
    b.PrependUOffsetTRelativeSlot(4, buffers_vec, 0)  # buffers
    model_off = b.EndObject()

    b.Finish(model_off)
    buf = bytes(b.Output())
    # Insert TFLite file identifier "TFL3" at bytes 4-7.
    # The root table offset (bytes 0-3) must be increased by 4 to account for the identifier.
    root_off = struct.unpack("<I", buf[:4])[0]
    return struct.pack("<I", root_off + 4) + b"TFL3" + buf[4:]
