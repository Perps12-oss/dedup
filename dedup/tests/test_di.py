import pytest

from dedup.core.di import Container


class A:
    pass


class B:
    def __init__(self, x: int = 0):
        self.x = x


def test_resolve_transient():
    c = Container()
    n = [0]

    def factory() -> B:
        n[0] += 1
        return B(n[0])

    c.register(B, factory, singleton=False)
    b1 = c.resolve(B)
    b2 = c.resolve(B)
    assert b1.x != b2.x


def test_resolve_singleton():
    c = Container()

    def factory() -> B:
        return B(42)

    c.register(B, factory, singleton=True)
    b1 = c.resolve(B)
    b2 = c.resolve(B)
    assert b1 is b2
    assert b1.x == 42


def test_register_instance():
    c = Container()
    inst = B(7)
    c.register_instance(B, inst)
    assert c.resolve(B) is inst


def test_resolve_missing():
    c = Container()
    with pytest.raises(KeyError):
        c.resolve(A)
