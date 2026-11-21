"""Windows standalone-Python OpenSSL file-I/O compatibility; verification stays enabled."""

import os, ssl
from pathlib import Path

_configured = False


def configure_tls():
    global _configured
    if _configured or os.name != "nt":
        return
    _configured = True
    original = ssl.SSLContext.load_verify_locations

    def load(self, cafile=None, capath=None, cadata=None):
        if cafile:
            raw = Path(cafile).read_bytes()
            original(
                self,
                cadata=raw.decode("ascii")
                if b"-----BEGIN CERTIFICATE-----" in raw
                else raw,
            )
        if capath or cadata is not None:
            return original(self, capath=capath, cadata=cadata)

    ssl.SSLContext.load_verify_locations = load
    import truststore

    truststore.inject_into_ssl()
