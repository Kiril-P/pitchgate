from flask import abort, redirect, render_template, request, url_for

from pitchgate.db import connect
from pitchgate.ideas.logic import LIMITS, IdeaNotFound, IdeaTextError
from pitchgate.ideas.store import create_idea, get_idea, list_ideas, revise_idea


def register_routes(app):
    @app.get("/")
    def home():
        connection = connect(app.config["DATABASE"])
        try:
            ideas = list_ideas(connection)
        finally:
            connection.close()
        return render_template(
            "home.html",
            ideas=ideas,
            error=None,
            form=_blank_form(),
            limits=LIMITS,
        )

    @app.post("/ideas")
    def create():
        form = _read_form()
        connection = connect(app.config["DATABASE"])
        try:
            try:
                idea = create_idea(
                    connection,
                    form["display_name"],
                    form["problem"],
                    form["audience"],
                    form["approach"],
                )
            except IdeaTextError as error:
                ideas = list_ideas(connection)
                return (
                    render_template(
                        "home.html",
                        ideas=ideas,
                        error=error.message,
                        form=form,
                        limits=LIMITS,
                    ),
                    400,
                )
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=idea["id"]))

    @app.get("/ideas/<int:idea_id>")
    def idea_detail(idea_id):
        connection = connect(app.config["DATABASE"])
        try:
            idea = get_idea(connection, idea_id)
        finally:
            connection.close()
        if idea is None:
            abort(404)
        current = idea["revisions"][0]
        return render_template(
            "idea.html",
            idea=idea,
            error=None,
            form=current,
            limits=LIMITS,
        )

    @app.post("/ideas/<int:idea_id>/revisions")
    def add_revision(idea_id):
        form = _read_form()
        connection = connect(app.config["DATABASE"])
        try:
            try:
                revise_idea(
                    connection,
                    idea_id,
                    form["problem"],
                    form["audience"],
                    form["approach"],
                )
            except IdeaNotFound:
                abort(404)
            except IdeaTextError as error:
                idea = get_idea(connection, idea_id)
                return (
                    render_template(
                        "idea.html",
                        idea=idea,
                        error=error.message,
                        form=form,
                        limits=LIMITS,
                    ),
                    400,
                )
        finally:
            connection.close()
        return redirect(url_for("idea_detail", idea_id=idea_id))


def _blank_form():
    return {
        "display_name": "",
        "problem": "",
        "audience": "",
        "approach": "",
    }


def _read_form():
    return {
        "display_name": request.form.get("display_name", ""),
        "problem": request.form.get("problem", ""),
        "audience": request.form.get("audience", ""),
        "approach": request.form.get("approach", ""),
    }
