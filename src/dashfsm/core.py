"""Framework-independent definitions and transactional navigation."""

import json
import warnings
from collections.abc import Callable, Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any

Data = dict[str, Any]


class DefinitionError(ValueError):
    """The state graph is invalid."""


class NavigationError(ValueError):
    """The requested navigation is unavailable."""


class ValidationError(ValueError):
    """An expected form or guard rejection, safe to show to the user."""


@dataclass(frozen=True)
class Patch:
    """Replace top-level values and explicitly remove keys."""

    values: Mapping[str, Any] = field(default_factory=dict)
    remove: tuple[str, ...] = ()


@dataclass
class Session:
    current: str
    context: Data = field(default_factory=dict)
    history: list[str] = field(default_factory=list)
    revision: int = 0

    def to_dict(self) -> Data:
        result = deepcopy(vars(self))
        json.dumps(result, allow_nan=False)
        return result

    @classmethod
    def from_dict(cls, value: Data) -> "Session":
        if not isinstance(value, dict) or set(value) != {
            "current",
            "context",
            "history",
            "revision",
        }:
            raise NavigationError("Invalid session structure")
        if (
            not isinstance(value["current"], str)
            or not isinstance(value["context"], dict)
            or not isinstance(value["history"], list)
            or not all(isinstance(name, str) for name in value["history"])
            or type(value["revision"]) is not int
            or value["revision"] < 0
        ):
            raise NavigationError("Invalid session values")
        json.dumps(value, allow_nan=False)
        return cls(**deepcopy(value))


@dataclass(frozen=True)
class Event:
    context: Data
    source: str | None
    destination: str
    action: str
    payload: Data = field(default_factory=dict)


Hook = Callable[[Event], Patch | Mapping[str, Any] | None]
Validator = Callable[[Event], str | None]
Guard = Callable[[Event], bool]


@dataclass(frozen=True)
class State:
    name: str
    layout: Any = None
    title: str | None = None
    validate: Validator | None = None
    on_enter: Hook | None = None
    on_exit: Hook | None = None

    def id(self, machine: str, component: str) -> dict[str, str]:
        """Use this ID with ordinary Dash Input/Output callback definitions."""
        return {"machine": machine, "state": self.name, "component": component}


@dataclass(frozen=True)
class Transition:
    source: str
    action: str
    destination: str
    label: str | None = None
    guard: Guard | None = None
    default: bool = False


class Machine:
    """Reusable graph definition; all mutable user data lives in Session."""

    RESERVED = frozenset({"back", "home", "reset", "next"})

    def __init__(
        self,
        states: list[State],
        transitions: list[Transition],
        *,
        initial: str,
        home: str | None = None,
        defaults: Mapping[str, Any] | None = None,
    ):
        self.states = {state.name: state for state in states}
        self.transitions = tuple(transitions)
        self.initial = initial
        self.home = initial if home is None else home
        self.defaults = deepcopy(dict(defaults or {}))
        json.dumps(self.defaults, allow_nan=False)
        if len(self.states) != len(states) or any(not s.name.strip() for s in states):
            raise DefinitionError("State names must be nonempty and unique")
        if initial not in self.states or self.home not in self.states:
            raise DefinitionError("Initial and home states must exist")
        keys: set[tuple[str, str]] = set()
        default_sources: set[str] = set()
        for transition in self.transitions:
            if transition.source not in self.states or transition.destination not in self.states:
                raise DefinitionError("Transition references an unknown state")
            key = (transition.source, transition.action)
            if key in keys or not transition.action.strip() or transition.action in self.RESERVED:
                raise DefinitionError("Actions must be unique per source and not reserved")
            keys.add(key)
            if transition.default:
                if transition.source in default_sources:
                    raise DefinitionError("Only one default transition is allowed per state")
                default_sources.add(transition.source)
        reachable = {initial}
        while True:
            expanded = reachable | {
                t.destination for t in self.transitions if t.source in reachable
            }
            if expanded == reachable:
                break
            reachable = expanded
        if missing := self.states.keys() - reachable:
            warnings.warn(f"Unreachable states: {', '.join(sorted(missing))}", stacklevel=2)

    def outgoing(self, name: str) -> tuple[Transition, ...]:
        return tuple(t for t in self.transitions if t.source == name)

    @staticmethod
    def _patch(context: Data, patch: Patch | Mapping[str, Any] | None) -> None:
        if patch is None:
            return
        if isinstance(patch, Patch):
            for key in patch.remove:
                context.pop(key, None)
            context.update(deepcopy(dict(patch.values)))
        else:
            context.update(deepcopy(dict(patch)))
        json.dumps(context, allow_nan=False)

    def _hook(self, hook: Hook | None, context: Data, event: Event) -> None:
        if hook:
            # Hook mutation cannot escape: only its explicit returned patch is applied.
            self._patch(context, hook(deepcopy(event)))

    def start(self) -> Session:
        context = deepcopy(self.defaults)
        event = Event(context, None, self.initial, "initial")
        self._hook(self.states[self.initial].on_enter, context, event)
        return Session(self.initial, context)

    def navigate(
        self,
        session: Session,
        action: str,
        *,
        patch: Patch | Mapping[str, Any] | None = None,
        payload: Data | None = None,
    ) -> Session:
        """Return a new session; failures never mutate the supplied session.

        Back/Home bypass form validation and transition guards: they are explicit
        machine operations, not graph edges. Guards apply to named/Next actions.
        """
        session = Session.from_dict(session.to_dict())
        if session.current not in self.states or any(h not in self.states for h in session.history):
            raise NavigationError("Session references an unknown state")
        source = self.states[session.current]
        context = deepcopy(self.defaults if action == "reset" else session.context)
        history = list(session.history)
        transition = None
        if action == "back":
            if not history:
                raise NavigationError("No previous state")
            destination = history.pop()
        elif action in {"home", "reset"}:
            destination = self.home if action == "home" else self.initial
            history = []
        else:
            transition = next(
                (
                    t
                    for t in self.outgoing(source.name)
                    if (t.default if action == "next" else t.action == action)
                ),
                None,
            )
            if transition is None:
                raise NavigationError(f"Action {action!r} is unavailable in {source.name!r}")
            destination = transition.destination
            history.append(source.name)
        if action != "reset":
            self._patch(context, patch)
        event = Event(context, source.name, destination, action, deepcopy(payload or {}))
        if transition:
            if source.validate and (error := source.validate(deepcopy(event))):
                raise ValidationError(error)
            if transition.guard and not transition.guard(deepcopy(event)):
                raise ValidationError("This transition is not allowed")
        if action != "reset":
            self._hook(source.on_exit, context, event)
        if transition and transition.guard and not transition.guard(deepcopy(event)):
            raise ValidationError("This transition is not allowed")
        self._hook(self.states[destination].on_enter, context, event)
        return Session(destination, context, history, session.revision + 1)
