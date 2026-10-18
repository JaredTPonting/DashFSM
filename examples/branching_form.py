"""Run with: uv run python examples/branching_form.py"""

from dash import Dash, Input, Output, dcc, html

from dashfsm import DashFSM, Machine, State, Transition

details = State(
    "details",
    title="Your details",
    layout=lambda data: html.Div(
        [
            html.Label(
                [
                    "Your name",
                    dcc.Input(id=flow.field_id("name"), value=data.get("name", "")),
                ]
            ),
            html.P(id=details.id("signup", "preview")),
        ]
    ),
    validate=lambda event: (
        None
        if event.action == "help" or str(event.context.get("name") or "").strip()
        else "Please enter your name."
    ),
)
review = State(
    "review",
    layout=lambda data: html.P(data["greeting"]),
    on_enter=lambda event: {"greeting": f"Hello, {event.context['name']}!"},
)
machine = Machine(
    states=[
        State("home", html.P("Start a short branching form.")),
        details,
        review,
        State("help", html.P("Enter the name you would like us to use.")),
        State("complete", html.P("Your form is complete.")),
    ],
    transitions=[
        Transition("home", "start", "details", default=True),
        Transition("details", "continue", "review", default=True),
        Transition("details", "help", "help", label="Get help"),
        Transition("help", "return", "details", default=True),
        Transition("review", "edit", "details", label="Edit answers"),
        Transition("review", "submit", "complete", label="Submit"),
    ],
    initial="home",
)
flow = DashFSM(machine, id="signup")
app = Dash(__name__)
app.layout = flow.layout
flow.register(app)


@app.callback(
    Output(details.id("signup", "preview"), "children"), Input(flow.field_id("name"), "value")
)
def preview(name):
    return f"Preview: {name or 'enter a name'}"


if __name__ == "__main__":
    app.run(debug=True)
