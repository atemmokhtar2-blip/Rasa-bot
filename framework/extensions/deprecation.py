from __future__ import annotations
import functools
import warnings

def deprecated(message: str, *, replacement: str | None = None, version: str | None = None):
    detail = message + (f"; use {replacement} instead" if replacement else "") + (f"; removal planned in {version}" if version else "")
    def decorate(function):
        @functools.wraps(function)
        def wrapped(*args, **kwargs):
            warnings.warn(detail, DeprecationWarning, stacklevel=2)
            return function(*args, **kwargs)
        return wrapped
    return decorate
