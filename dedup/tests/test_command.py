from dedup.core.command import Command


def test_command_execute_when_allowed():
    out = []

    c = Command(lambda: out.append(1), can_execute=lambda: True)
    c.execute()
    assert out == [1]


def test_command_respects_can_execute():
    out = []

    c = Command(lambda: out.append(1), can_execute=lambda: False)
    c.execute()
    assert out == []


def test_command_can_execute_changed():
    allow = [False]

    c = Command(lambda: None, can_execute=lambda: allow[0])
    changed = []
    c.subscribe_can_execute_changed(lambda: changed.append(1))
    assert c.can_execute() is False
    allow[0] = True
    c.notify_can_execute_changed()
    assert c.can_execute() is True
    assert changed == [1]
