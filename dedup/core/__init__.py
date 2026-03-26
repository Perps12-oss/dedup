"""Core primitives: reactive observables, commands, dependency injection."""

from .command import Command
from .di import Container, get_container, set_container
from .observable import Observable, Property

__all__ = [
    "Command",
    "Container",
    "Observable",
    "Property",
    "get_container",
    "set_container",
]
