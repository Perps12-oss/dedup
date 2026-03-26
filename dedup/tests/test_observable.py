from dedup.core.observable import Observable, computed


def test_observable_set_notifies():
    o = Observable(1)
    seen = []

    o.subscribe(lambda v: seen.append(v))
    o.set(2)
    assert seen == [2]


def test_observable_same_value_skips_notify():
    o = Observable(1)
    calls = []

    def cb(_):
        calls.append(1)

    o.subscribe(cb)
    o.set(1)
    assert calls == []


def test_observable_unsubscribe():
    o = Observable(0)
    calls = []

    def cb(v):
        calls.append(v)

    unsub = o.subscribe(cb)
    o.set(1)
    unsub()
    o.set(2)
    assert calls == [1]


def test_computed_updates():
    a = Observable(1)
    b = Observable(2)
    c = computed(a, b, compute=lambda x, y: x + y)
    assert c.get() == 3
    a.set(10)
    assert c.get() == 12
