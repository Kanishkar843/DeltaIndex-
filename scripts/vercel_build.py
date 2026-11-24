from pathlib import Path
import hashlib
import shutil
import urllib.request

shutil.copytree(Path("frontend/dist"), Path("public"), dirs_exist_ok=True)
root = Path("models/minilm")
root.mkdir(parents=True, exist_ok=True)
base = "https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2/resolve/1110a243fdf4706b3f48f1d95db1a4f5529b4d41/"
for remote, local in [
    ("onnx/model_quint8_avx2.onnx", "model.onnx"),
    ("tokenizer.json", "tokenizer.json"),
    ("README.md", "MODEL_CARD.md"),
]:
    target = root / local
    if not target.exists():
        with urllib.request.urlopen(base + remote, timeout=120) as response:
            target.write_bytes(response.read())
assert (
    hashlib.sha256((root / "model.onnx").read_bytes()).hexdigest()
    == "b941bf19f1f1283680f449fa6a7336bb5600bdcd5f84d10ddc5cd72218a0fd21"
)
shutil.copyfile("docs/third_party/Apache-2.0.txt", root / "LICENSE")
