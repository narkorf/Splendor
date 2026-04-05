"""Web backend for the hosted Splendor experience."""

__all__ = ["create_app"]


def create_app():
    from .app import create_app as _create_app

    return _create_app()
