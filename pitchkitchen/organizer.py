import hmac
from datetime import date

from flask import abort, render_template, request

from pitchkitchen.cohort.logic import metrics, rows
from pitchkitchen.db import connect
from pitchkitchen.ideas.logic import station_name
from pitchkitchen.ideas.store import list_ideas
from pitchkitchen.review.store import gates_passed, verdicts_for


def register_organizer(app):
    @app.get("/organizer")
    def organizer():
        expected = app.config.get("ORGANIZER_KEY", "")
        if not expected:
            abort(404)
        given = request.args.get("key", "")
        if not hmac.compare_digest(given.encode("utf-8"), expected.encode("utf-8")):
            return render_template("organizer.html", locked=True, wrong=bool(given)), 403

        today = app.config.get("TODAY") or date.today()
        connection = connect(app.config["DATABASE"])
        try:
            ideas = list_ideas(connection)
            found = verdicts_for(connection, [rid for idea in ideas for rid in idea["branch_ids"]])
            for idea in ideas:
                idea["labels"] = [found[rid]["label"] if rid in found else "PENDING" for rid in idea["branch_ids"]]
                idea["gates_passed"] = gates_passed(connection, idea["id"])
        finally:
            connection.close()

        table = rows(ideas, today)
        for row in table:
            row["station_name"] = station_name(row["station"])
        return render_template("organizer.html", locked=False, rows=table, metrics=metrics(ideas, today), today=today)
