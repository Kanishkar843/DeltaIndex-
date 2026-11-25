"""Optional actual-model check; run with the ONNX deployment dependencies installed."""
import numpy as np
from app.core import Embedder

model = Embedder('onnx')
a = np.array(model.encode('Python backend engineer'))
b = np.array(model.encode('Python backend engineer'))
c = np.array(model.encode('Gardening and flower arranging'))
assert a.shape == (384,)
assert np.isfinite(a).all()
assert abs(float(np.linalg.norm(a)) - 1) < 1e-6
assert np.allclose(a, b)
assert float(a @ b) > float(a @ c)
print('PASS: actual ONNX shape, finite unit vector, reproducibility, semantic ordering')
