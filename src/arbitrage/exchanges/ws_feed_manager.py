"""Simple manager for websocket feeders.

Allows registering a feeder instance under an exchange name so adapters can
query live snapshots produced by feeders.
"""
from typing import Optional

_FEEDS: dict[str, object] = {}


def register_feeder(exchange_name: str, feeder: object) -> None:
    _FEEDS[exchange_name.lower()] = feeder


def get_feeder(exchange_name: str) -> Optional[object]:
    return _FEEDS.get(exchange_name.lower())


def unregister_feeder(exchange_name: str) -> None:
    _FEEDS.pop(exchange_name.lower(), None)


def list_feeders() -> dict[str, object]:
    """Return a shallow copy of the registered feeders map.

    Keys are lower-cased exchange names.
    """
    return dict(_FEEDS)
