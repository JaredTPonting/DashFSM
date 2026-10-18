import json
import runpy
from pathlib import Path

from dash import Dash

from dashfsm import DashFSM, Machine, State, Transition


def test_mount_and_dash_endpoints():
    machine = Machine(
        [State("a", "First"), State("b", lambda data: "Second")],
        [Transition("a", "go", "b", default=True)],
        initial="a",
    )
    flow = DashFSM(machine)
    app = Dash(__name__)
    app.layout = flow.layout
    flow.register(app)
    client = app.server.test_client()
    assert client.get("/").status_code == 200
    assert client.get("/_dash-layout").status_code == 200
    assert client.get("/_dash-dependencies").status_code == 200
    assert len(app.callback_map) == 1
    assert flow.render(machine.start()).to_plotly_json()["type"] == "Section"


def test_multiple_machine_ids_do_not_collide():
    machine = Machine([State("a")], [], initial="a")
    first, second = DashFSM(machine, id="first"), DashFSM(machine, id="second")
    assert first.field_id("name") != second.field_id("name")
    app = Dash(__name__)
    from dash import html

    app.layout = html.Div([first.layout(), second.layout()])
    first.register(app)
    second.register(app)
    assert len(app.callback_map) == 2


def test_example_navigation_through_dash_callback_endpoint():
    example = runpy.run_path(str(Path(__file__).parents[1] / "examples" / "branching_form.py"))
    app = example["app"]
    flow = example["flow"]
    client = app.server.test_client()
    callback_key = next(key for key in app.callback_map if "signup-session" in key)

    def request(data=None, action=None, values=None):
        response = client.post(
            "/_dash-update-component",
            json={
                "output": callback_key,
                "outputs": [
                    {"id": "signup-session", "property": "data"},
                    {"id": "signup-view", "property": "children"},
                    {"id": "signup-error", "property": "children"},
                ],
                "inputs": [
                    {
                        "id": '{"action":["ALL"],"fsm":"signup"}',
                        "property": "n_clicks",
                        "value": [1] if action else [],
                    }
                ],
                "state": [
                    {"id": "signup-session", "property": "data", "value": data},
                    {
                        "id": '{"field":["ALL"],"fsm":"signup"}',
                        "property": "id",
                        "value": [flow.field_id("name")] if values is not None else [],
                    },
                    {
                        "id": '{"field":["ALL"],"fsm":"signup"}',
                        "property": "value",
                        "value": values or [],
                    },
                ],
                "changedPropIds": [
                    json.dumps(flow.action_id(action), sort_keys=True, separators=(",", ":"))
                    + ".n_clicks"
                ]
                if action
                else [],
            },
        )
        assert response.status_code == 200, response.data
        return response.get_json()["response"]

    home = request()["signup-session"]["data"]
    assert home["current"] == "home"
    details = request(home, "start")["signup-session"]["data"]
    failed = request(details, "continue", [""])
    assert failed["signup-error"]["children"] == "Please enter your name."
    assert "signup-session" not in failed
    help_session = request(details, "help", [""])["signup-session"]["data"]
    assert help_session["current"] == "help"
    back = request(help_session, "back")["signup-session"]["data"]
    reviewed = request(back, "continue", ["Ada"])["signup-session"]["data"]
    assert reviewed["context"]["greeting"] == "Hello, Ada!"
    assert request(reviewed, "submit")["signup-session"]["data"]["current"] == "complete"
    restored = request(reviewed)["signup-session"]["data"]
    assert restored == reviewed
    reset = request(reviewed, "reset")["signup-session"]["data"]
    assert reset["current"] == "home" and reset["context"] == {}
