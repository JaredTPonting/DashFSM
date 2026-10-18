import pytest

from dashfsm import (
    DefinitionError,
    Machine,
    NavigationError,
    Patch,
    Session,
    State,
    Transition,
    ValidationError,
)


def make_machine(**kwargs):
    return Machine(
        [
            State("home"),
            State("form", **kwargs),
            State("review", on_enter=lambda e: {"summary": e.context.get("name")}),
        ],
        [
            Transition("home", "start", "form", default=True),
            Transition("form", "continue", "review", default=True),
            Transition("form", "cancel", "home"),
        ],
        initial="home",
        defaults={"plan": "basic"},
    )


def test_journey_data_hooks_history_and_reset():
    machine = make_machine(on_exit=lambda e: {"name": e.context["name"].strip()})
    first = machine.start()
    form = machine.navigate(first, "next")
    review = machine.navigate(form, "continue", patch={"name": " Ada "})
    assert review.context == {"name": "Ada", "summary": "Ada", "plan": "basic"}
    assert review.history == ["home", "form"]
    assert first.context == {"plan": "basic"}
    back = machine.navigate(review, "back")
    assert back.current == "form"
    assert back.context["name"] == "Ada"
    home = machine.navigate(review, "home")
    assert home.current == "home" and home.history == []
    reset = machine.navigate(review, "reset", patch={"ignored": True})
    assert reset.context == {"plan": "basic"} and reset.history == []
    assert reset.revision == review.revision + 1


def test_validation_and_hook_failure_leave_input_unchanged():
    machine = make_machine(
        validate=lambda e: "Name required" if not e.context.get("name") else None
    )
    form = machine.navigate(machine.start(), "start")
    snapshot = form.to_dict()
    with pytest.raises(ValidationError, match="Name required"):
        machine.navigate(form, "continue")
    assert form.to_dict() == snapshot

    def fail(event):
        event.context["leaked"] = True
        raise RuntimeError("hook failed")

    machine = make_machine(on_exit=fail)
    with pytest.raises(RuntimeError, match="hook failed"):
        machine.navigate(form, "continue", patch={"name": "Ada"})
    assert form.to_dict() == snapshot


def test_guard_checks_normalized_outgoing_context():
    machine = Machine(
        [State("a", on_exit=lambda e: {"allowed": False}), State("b")],
        [Transition("a", "go", "b", guard=lambda e: e.context["allowed"])],
        initial="a",
    )
    session = machine.start()
    with pytest.raises(ValidationError):
        machine.navigate(session, "go", patch={"allowed": True})
    assert session.context == {}


def test_initial_hook_payload_and_isolation():
    events = []

    def enter(event):
        events.append(event)
        return {"visited": True}

    machine = Machine(
        [State("a", on_enter=enter), State("b", on_enter=enter)],
        [Transition("a", "go", "b")],
        initial="a",
    )
    first, second = machine.start(), machine.start()
    machine.navigate(first, "go", patch={"answer": [1]}, payload={"reason": "test"})
    assert events[0].source is None and events[0].action == "initial"
    assert events[-1].payload == {"reason": "test"}
    assert second.context == {"visited": True}
    assert "answer" not in first.context


def test_patch_removal_and_serialization():
    machine = make_machine()
    result = machine.navigate(machine.start(), "start", patch=Patch({"none": None}, ("plan",)))
    assert result.context == {"none": None}
    assert Session.from_dict(result.to_dict()) == result
    with pytest.raises(TypeError):
        machine.navigate(result, "continue", patch={"bad": object()})


@pytest.mark.parametrize(
    "value",
    [
        {},
        {"current": "home", "context": [], "history": [], "revision": 0},
        {"current": "home", "context": {}, "history": [], "revision": True},
    ],
)
def test_invalid_browser_session(value):
    with pytest.raises(NavigationError):
        Session.from_dict(value)


def test_invalid_graphs_and_actions():
    with pytest.raises(DefinitionError):
        Machine([State("a"), State("a")], [], initial="a")
    with pytest.raises(DefinitionError):
        Machine([State("a")], [Transition("a", "go", "missing")], initial="a")
    with pytest.raises(DefinitionError):
        Machine([State("a")], [Transition("a", "back", "a")], initial="a")
    with pytest.raises(DefinitionError):
        Machine(
            [State("a")],
            [Transition("a", "x", "a", default=True), Transition("a", "y", "a", default=True)],
            initial="a",
        )
    machine = make_machine()
    with pytest.raises(NavigationError):
        machine.navigate(machine.start(), "back")
    with pytest.raises(NavigationError):
        machine.navigate(machine.start(), "unknown")


def test_cycles_terminal_states_and_unreachable_diagnostic():
    with pytest.warns(UserWarning, match="Unreachable"):
        machine = Machine(
            [State("a"), State("unused")], [Transition("a", "loop", "a")], initial="a"
        )
    assert machine.navigate(machine.start(), "loop").history == ["a"]
    assert machine.outgoing("unused") == ()
