"""Beeper UI Flask application."""

from flask import Flask, render_template

app = Flask(__name__)


@app.route("/")
def index() -> str:
    """Render the main page."""
    return render_template("base.html")


@app.route("/health")
def health() -> dict[str, str]:
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    app.run(debug=True)
