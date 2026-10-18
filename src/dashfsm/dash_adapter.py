"""Small Dash adapter using browser session storage for non-sensitive answers."""

import logging
from copy import deepcopy
from typing import Any

from dash import ALL, Dash, Input, Output, ctx, dcc, html, no_update
from dash import State as DashState
from dash.exceptions import PreventUpdate

from .core import Machine, NavigationError, Session, ValidationError

logger = logging.getLogger(__name__)


class DashFSM:
    """Mount once per app/ID. Layout factories receive a copied context dict.

    Fields using ``field_id`` have their ``value`` collected on navigation.
    Ordinary callbacks can use State.id() for namespaced local components.
    """

    def __init__(self, machine: Machine, *, id: str = "dashfsm"):
        self.machine = machine
        self.id = id

    def field_id(self, key: str) -> dict[str, str]:
        return {"fsm": self.id, "field": key}

    def action_id(self, action: str) -> dict[str, str]:
        return {"fsm": self.id, "action": action}

    def layout(self):
        # Start in a callback, not here: layout evaluation may happen repeatedly.
        return html.Div(
            [
                dcc.Store(id=f"{self.id}-session", storage_type="session"),
                html.Div(id=f"{self.id}-error", role="alert"),
                html.Div(id=f"{self.id}-view"),
            ]
        )

    def render(self, session: Session):
        state = self.machine.states[session.current]
        body = state.layout(deepcopy(session.context)) if callable(state.layout) else state.layout
        controls = [
            html.Button(
                t.label or ("Next" if t.default else t.action),
                id=self.action_id(t.action),
                n_clicks=0,
            )
            for t in self.machine.outgoing(state.name)
        ]
        controls.extend(
            [
                html.Button("Back", id=self.action_id("back"), disabled=not session.history),
                html.Button("Home", id=self.action_id("home")),
                html.Button("Reset", id=self.action_id("reset")),
            ]
        )
        nav_attributes: dict[str, Any] = {"aria-label": "Form navigation"}
        return html.Section(
            [
                html.H2(state.title or state.name),
                body,
                html.Nav(controls, **nav_attributes),
            ]
        )

    def register(self, app: Dash) -> None:
        app.config.suppress_callback_exceptions = True

        @app.callback(
            Output(f"{self.id}-session", "data"),
            Output(f"{self.id}-view", "children"),
            Output(f"{self.id}-error", "children"),
            Input({"fsm": self.id, "action": ALL}, "n_clicks"),
            DashState(f"{self.id}-session", "data"),
            DashState({"fsm": self.id, "field": ALL}, "id"),
            DashState({"fsm": self.id, "field": ALL}, "value"),
        )
        def navigate(clicks, data, field_ids, values):
            try:
                session = Session.from_dict(data) if data is not None else self.machine.start()
                if session.current not in self.machine.states:
                    raise NavigationError("Unknown current state; clear browser session storage")
                if isinstance(ctx.triggered_id, dict):
                    if not any(clicks):
                        raise PreventUpdate
                    session = self.machine.navigate(
                        session,
                        ctx.triggered_id["action"],
                        patch={item["field"]: value for item, value in zip(field_ids, values)},
                    )
                return session.to_dict(), self.render(session), ""
            except (ValidationError, NavigationError) as error:
                return no_update, no_update, str(error)
            except PreventUpdate:
                raise
            except Exception:
                logger.exception("DashFSM navigation failed")
                return no_update, no_update, "Unable to change state. Please try again."
