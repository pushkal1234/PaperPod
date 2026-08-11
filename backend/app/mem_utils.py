"""Return freed heap back to the OS after heavy jobs.

Python + glibc keep freed memory inside the process (RSS plateaus) instead of
handing it back to the OS, so after a PDF/vision/TTS job idle RSS can stay high.
gc.collect() drops Python refs; malloc_trim(0) forces glibc to release the freed
arena space. Best-effort and no-op on non-glibc platforms (e.g. macOS dev, musl).
"""
import ctypes
import ctypes.util
import gc
import logging

logger = logging.getLogger("paperpod")

# None = not tried yet, False = unavailable (skip), else the resolved C function.
_malloc_trim = None


def _resolve_malloc_trim():
    global _malloc_trim
    if _malloc_trim is not None:
        return _malloc_trim
    for name in ("libc.so.6", ctypes.util.find_library("c")):
        if not name:
            continue
        try:
            fn = ctypes.CDLL(name, use_errno=True).malloc_trim
            fn.argtypes = [ctypes.c_size_t]
            fn.restype = ctypes.c_int
            _malloc_trim = fn
            return fn
        except (OSError, AttributeError):
            continue
    _malloc_trim = False  # remember: not glibc, don't probe again
    return False


def trim_memory():
    """gc.collect() + glibc malloc_trim(0). Best-effort, never raises."""
    gc.collect()
    fn = _resolve_malloc_trim()
    if not fn:
        return
    try:
        fn(0)
    except Exception:
        pass
