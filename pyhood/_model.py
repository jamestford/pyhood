"""Shared base for pyhood's dataclass models."""

from __future__ import annotations

import dataclasses
from typing import Any


class Model:
    """Base for the models. A wrong field name is answered with the right ones.

    Code that reads a field that does not exist is usually guessing at a
    name, often Robinhood's own (`average_buy_price` for `average_cost`).
    The stock AttributeError says only that the guess was wrong. This one
    lists what the model has, so the caller can fix it without going to
    look.
    """

    def __getattr__(self, name: str) -> Any:
        # Only reached when normal lookup has already failed. Dunder
        # lookups come from Python itself (copy, pickle), not from a
        # caller guessing a field, so they get the plain error.
        if name.startswith("__") and name.endswith("__"):
            raise AttributeError(name)
        cls = type(self)
        fields = [f.name for f in dataclasses.fields(self)]  # type: ignore[arg-type]
        properties = [
            attr for attr, value in vars(cls).items() if isinstance(value, property)
        ]
        # No closing full stop: Python 3.12+ appends its own sentence.
        message = f"{cls.__name__} has no field {name!r}. Its fields are: {', '.join(fields)}"
        if properties:
            message += f". Computed: {', '.join(properties)}"
        # name and obj let Python 3.12+ add "Did you mean ...?" for a near miss.
        raise AttributeError(message, name=name, obj=self)
