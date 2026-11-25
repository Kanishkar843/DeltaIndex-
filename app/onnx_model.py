from pathlib import Path
import hashlib
import os
import numpy as np
import onnxruntime as ort
from tokenizers import Tokenizer

MODEL_SHA256 = "b941bf19f1f1283680f449fa6a7336bb5600bdcd5f84d10ddc5cd72218a0fd21"


class MiniLMOnnx:
    """Pinned quantized MiniLM with masked mean pooling and unit normalization."""

    def __init__(self):
        root = Path(os.getenv("ONNX_MODEL_PATH", "models/minilm"))
        model = root / "model.onnx"
        if hashlib.sha256(model.read_bytes()).hexdigest() != MODEL_SHA256:
            raise ValueError("MiniLM ONNX checksum mismatch")
        self.tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=256)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(
            str(model), options, providers=["CPUExecutionProvider"]
        )

    def encode(self, text, normalize_embeddings=True):
        encoded = self.tokenizer.encode(text)
        inputs = {
            "input_ids": np.array([encoded.ids], dtype=np.int64),
            "attention_mask": np.array([encoded.attention_mask], dtype=np.int64),
            "token_type_ids": np.array([encoded.type_ids], dtype=np.int64),
        }
        output = self.session.run(
            None, {i.name: inputs[i.name] for i in self.session.get_inputs()}
        )[0]
        mask = inputs["attention_mask"][..., None]
        vector = (output * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1)
        vector = vector[0]
        return (
            vector / max(float(np.linalg.norm(vector)), 1e-12)
            if normalize_embeddings
            else vector
        )
