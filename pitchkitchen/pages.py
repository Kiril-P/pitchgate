from datetime import date

from flask import Response, abort, redirect, render_template, request, url_for

from pitchkitchen.db import connect
from pitchkitchen.ideas.logic import (
    DEFAULT_LEVEL,
    LEVELS,
    LIMITS,
    TONES,
    IdeaClosed,
    IdeaNotFound,
    IdeaTextError,
    founder_text,
    other_versions,
    rail,
    station_name,
)
from pitchkitchen.ideas.store import (
    add_answer,
    add_evidence,
    create_idea,
    delete_idea,
    edit_answer,
    evidence_for,
    get_idea,
    get_idea_by_token,
    list_ideas,
    set_shared,
    set_station,
    set_status,
)
from pitchkitchen.pack import render_pack
from pitchkitchen.review.coach import ChefUnavailable, find_facts, suggest_one_liners, suggest_searches, suggest_sparks
from pitchkitchen.review.logic import (
    SERVE_MIN_LOGS,
    SESSION_ANSWERS,
    STARTER_LEVELS,
    answers_left,
    can_serve,
    starter_gate,
)
from pitchkitchen.review.service import (
    GateNotReady,
    NotServable,
    conversations,
    gate_status,
    run_gate,
    run_round,
    serve,
    sessions_for,
    step_for,
    write_pack,
)
from pitchkitchen.review.store import (
    chef_for,
    forget,
    jev_calls_used,
    latest_homework,
    latest_of,
    verdicts_for,
)

COOKIE = "pk_ideas"
COOKIE_AGE = 60 * 60 * 24 * 365

BOARDS = (
    ("kitchen", "In the kitchen", ("cooking", "parked")),
    ("served", "Served", ("served",)),
    ("binned", "Binned", ("binned",)),
)

EVIDENCE_FIELDS = ("kind", "who", "role", "spoken_on", "today_they", "paid", "quote", "source")


def register_routes(app):
    def settings():
        return {
            "jev_key": app.config.get("TYPESAFE_API_KEY", ""),
            "jev_budget": app.config["JEV_BUDGET_PER_IDEA"],
            "chef_key": app.config.get("COACH_API_KEY", ""),
            "chef_model": app.config["COACH_MODEL"],
            "chef_url": app.config["COACH_URL"],
        }

    def snapshot(connection, idea):
        return founder_text(idea["branch"], evidence_for(connection, idea["id"]))

    def play(connection, idea):
        result = run_round(
            connection,
            [revision["id"] for revision in idea["branch"]],
            snapshot(connection, idea),
            settings(),
            jev_transport=app.config.get("JEV_TRANSPORT"),
            chef_transport=app.config.get("CHEF_TRANSPORT"),
            idea_id=idea["id"],
            tone=idea["tone"],
            level=idea["level"],
        )
        if result["step"] == "binned":
            set_status(connection, idea["id"], "binned")
        set_station(connection, idea["id"], "tasting" if result["step"] == "homework" else "grill")
        return result

    def render_home(connection, error, form, status=200):
        ideas = list_ideas(connection)
        found = verdicts_for(connection, [idea["head_id"] for idea in ideas])
        for idea in ideas:
            idea["verdict"] = found.get(idea["head_id"])
            idea["station_name"] = station_name(idea["station"])
        mine = set(my_tokens())
        boards = [
            {
                "key": key,
                "title": title,
                "ideas": [i for i in ideas if i["token"] in mine and i["status"] in statuses],
            }
            for key, title, statuses in BOARDS
        ]
        cohort = [i for i in ideas if i["shared"] and i["token"] not in mine]
        page = render_template(
            "home.html",
            boards=boards,
            cohort=cohort,
            mine=sum(len(board["ideas"]) for board in boards),
            error=error,
            form=form,
            limits=LIMITS,
            tones=TONES,
            levels=LEVELS,
            can_suggest=bool(app.config.get("COACH_API_KEY")),
        )
        return page, status

    def render_idea(
        connection, idea, error=None, status=200, evidence_form=None, evidence_error=None, pack_error=None
    ):
        ids = [revision["id"] for revision in idea["branch"]]
        found = verdicts_for(connection, ids)
        chef = chef_for(connection, ids)
        versions = other_versions(idea["revisions"], idea["branch"])
        for revision in idea["branch"]:
            revision["verdict"] = found.get(revision["id"])
            revision["chef"] = chef.get(revision["id"], {}).get("turn")
            revision["versions"] = versions.get(revision["id"], 0)
        head = idea["branch"][-1]
        sessions = sessions_for(connection, idea["id"])
        step = step_for(connection, ids, sessions)
        head_chef = chef.get(head["id"], {})
        paused = None
        if head["verdict"] is None or head["verdict"]["label"] == "PENDING":
            paused = "jev"
        elif head["chef"] is None or (step == "homework" and "homework" not in head_chef):
            paused = "chef"
        evidence = evidence_for(connection, idea["id"])
        talks = conversations(evidence)
        gate = gate_status(connection, idea["id"], evidence)
        pivot_from = get_idea(connection, idea["pivot_of"]) if idea["pivot_of"] else None
        label = head["verdict"]["label"] if head["verdict"] else "PENDING"
        verified = idea["status"] == "served"
        pack = latest_of(connection, ids, "starter_pack")
        pack_stale = pack is not None and (
            pack["revision_id"] != head["id"] or pack["body"]["logs"] != len(evidence) or pack["body"]["verified"] != verified
        )
        page = render_template(
            "idea.html",
            idea=idea,
            stations=rail(idea["station"]),
            head=head,
            step=step,
            paused=paused,
            closed=idea["status"] in ("served", "binned"),
            sessions=sessions,
            homework=latest_homework(connection, ids),
            polished=head_chef.get("polished"),
            next_steps=head_chef.get("next_steps"),
            answers_left=answers_left(len(ids) - 1, sessions),
            session_answers=SESSION_ANSWERS,
            evidence=evidence,
            talks=talks,
            gate=gate,
            servable=can_serve(label, len(talks)),
            serve_min_logs=SERVE_MIN_LOGS,
            starter=idea["level"] in STARTER_LEVELS,
            starter_gate=starter_gate(idea["level"], sessions),
            can_search=bool(app.config.get("COACH_API_KEY")),
            verified=verified,
            pack=pack["body"] if pack else None,
            pack_stale=pack_stale,
            pack_error=pack_error,
            pivot_from=pivot_from,
            jev_used=jev_calls_used(connection, idea["id"]),
            jev_budget=app.config["JEV_BUDGET_PER_IDEA"],
            error=error,
            evidence_form=evidence_form or {},
            evidence_error=evidence_error,
            limits=LIMITS,
            today=(app.config.get("TODAY") or date.today()).isoformat(),
        )
        return page, status

    def load(connection, token):
        idea = get_idea_by_token(connection, token)
        if idea is None:
            abort(404)
        return idea

    def back_to(token):
        return redirect(url_for("idea_detail", token=token))

    @app.get("/")
    def home():
        connection = connect(app.config["DATABASE"])
        try:
            form = _pitch_form()
            source = get_idea_by_token(connection, request.args.get("pivot", ""))
            if source is not None:
                pitch = source["branch"][0]
                form.update(
                    display_name=source["display_name"],
                    one_liner=pitch["one_liner"],
                    story=pitch["story"],
                    tone=source["tone"],
                    level=source["level"],
                    pivot=source["token"],
                    pivot_title=pitch["one_liner"],
                )
            return render_home(connection, None, form)
        finally:
            connection.close()

    @app.post("/prep/suggest")
    def suggest():
        rough = " ".join(
            part.strip() for part in (request.form.get("one_liner", ""), request.form.get("story", "")) if part.strip()
        )
        if not rough:
            return render_template("_suggestions.html", error="Write a rough idea or story first.", suggestions=[])
        try:
            suggestions = suggest_one_liners(
                rough[:2000],
                app.config.get("COACH_API_KEY", ""),
                app.config["COACH_MODEL"],
                app.config["COACH_URL"],
                transport=app.config.get("CHEF_TRANSPORT"),
            )
        except ChefUnavailable:
            return render_template("_suggestions.html", error="Chef is busy. Try again in a moment.", suggestions=[])
        return render_template("_suggestions.html", error=None, suggestions=[{"one_liner": text} for text in suggestions])

    @app.post("/prep/spark")
    def spark():
        about = request.form.get("about", "").strip()
        if not about:
            return render_template("_suggestions.html", error="Tell Chef a little about your week first.", suggestions=[])
        try:
            sparks = suggest_sparks(
                about[:2000],
                app.config.get("COACH_API_KEY", ""),
                app.config["COACH_MODEL"],
                app.config["COACH_URL"],
                transport=app.config.get("CHEF_TRANSPORT"),
            )
        except ChefUnavailable:
            return render_template("_suggestions.html", error="Chef is busy. Try again in a moment.", suggestions=[])
        return render_template("_suggestions.html", error=None, suggestions=sparks)

    @app.post("/ideas")
    def create():
        form = _pitch_form(request.form)
        connection = connect(app.config["DATABASE"])
        try:
            pivot = get_idea_by_token(connection, form["pivot"]) if form["pivot"] else None
            try:
                idea = create_idea(
                    connection,
                    form["display_name"],
                    form["one_liner"],
                    form["story"],
                    tone=form["tone"],
                    shared=form["shared"],
                    pivot_of=pivot["id"] if pivot else None,
                    consent=form["consent"],
                    level=form["level"],
                )
            except IdeaTextError as error:
                return render_home(connection, error.message, form, 400)
            play(connection, idea)
        finally:
            connection.close()
        response = back_to(idea["token"])
        _remember(response, idea["token"])
        return response

    @app.get("/i/<token>")
    def idea_detail(token):
        connection = connect(app.config["DATABASE"])
        try:
            return render_idea(connection, load(connection, token))
        finally:
            connection.close()

    @app.post("/i/<token>/answers")
    def answer(token):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            ids = [revision["id"] for revision in idea["branch"]]
            if step_for(connection, ids, sessions_for(connection, idea["id"])) != "open":
                return render_idea(connection, idea, "This session is over. Log real conversations to open the next one.", 409)
            try:
                idea = add_answer(connection, idea["id"], request.form.get("answer", ""))
            except IdeaClosed:
                return render_idea(connection, idea, "This idea is closed.", 409)
            except IdeaTextError as error:
                return render_idea(connection, idea, error.message, 400)
            play(connection, idea)
        finally:
            connection.close()
        return back_to(token)

    @app.post("/i/<token>/answers/<int:revision_id>/edit")
    def edit(token, revision_id):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            try:
                idea = edit_answer(connection, idea["id"], revision_id, request.form.get("answer", ""))
            except IdeaNotFound:
                abort(404)
            except IdeaClosed:
                return render_idea(connection, idea, "This idea is closed.", 409)
            except IdeaTextError as error:
                return render_idea(connection, idea, error.message, 400)
            play(connection, idea)
        finally:
            connection.close()
        return back_to(token)

    @app.post("/i/<token>/retry")
    def retry(token):
        connection = connect(app.config["DATABASE"])
        try:
            play(connection, load(connection, token))
        finally:
            connection.close()
        return back_to(token)

    @app.post("/i/<token>/evidence")
    def log_evidence(token):
        form = {field: request.form.get(field, "") for field in EVIDENCE_FIELDS}
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            try:
                add_evidence(
                    connection,
                    idea["id"],
                    sessions_for(connection, idea["id"]),
                    form,
                    today=app.config.get("TODAY"),
                )
            except IdeaClosed:
                return render_idea(connection, idea, "This idea is closed.", 409)
            except IdeaTextError as error:
                return render_idea(connection, idea, status=400, evidence_form=form, evidence_error=error.message)
            if idea["station"] == "prep":
                set_station(connection, idea["id"], "tasting")
        finally:
            connection.close()
        return redirect(url_for("idea_detail", token=token) + "#tasting")

    @app.post("/i/<token>/facts/search")
    def search_facts(token):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            kept = {entry["quote"] for entry in evidence_for(connection, idea["id"]) if entry["kind"] == "fact"}
        finally:
            connection.close()
        pitch = idea["branch"][0]
        try:
            facts = find_facts(
                pitch["one_liner"],
                pitch["story"],
                app.config.get("COACH_API_KEY", ""),
                app.config["COACH_MODEL"],
                transport=app.config.get("SEARCH_TRANSPORT"),
            )
        except ChefUnavailable:
            try:
                searches = suggest_searches(
                    pitch["one_liner"],
                    pitch["story"],
                    app.config.get("COACH_API_KEY", ""),
                    app.config["COACH_MODEL"],
                    app.config["COACH_URL"],
                    transport=app.config.get("CHEF_TRANSPORT"),
                )
            except ChefUnavailable:
                return render_template(
                    "_facts.html", idea=idea, facts=[], error="Chef couldn't search the web or suggest searches right now. Try again later."
                )
            return render_template("_facts.html", idea=idea, facts=[], searches=searches, error=None)
        fresh = [fact for fact in facts if fact["fact"] not in kept]
        if not fresh:
            return render_template("_facts.html", idea=idea, facts=[], error="Chef found nothing new. You already kept these facts.")
        return render_template("_facts.html", idea=idea, facts=fresh, error=None)

    @app.post("/i/<token>/facts")
    def keep_facts(token):
        """Facts from a search are not stored until the founder ticks them; each comes back
        with its text, link, and site as numbered form fields."""
        today = (app.config.get("TODAY") or date.today()).isoformat()
        picked = [
            {
                "kind": "fact",
                "quote": request.form.get("fact_" + number, ""),
                "source": request.form.get("source_" + number, ""),
                "who": request.form.get("site_" + number, ""),
                "spoken_on": today,
            }
            for number in request.form.getlist("keep")
        ]
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            if not picked:
                return render_idea(
                    connection, idea, status=400, evidence_form={"kind": "fact"}, evidence_error="Tick at least one fact to keep."
                )
            try:
                for fields in picked:
                    add_evidence(connection, idea["id"], sessions_for(connection, idea["id"]), fields, today=app.config.get("TODAY"))
            except IdeaClosed:
                return render_idea(connection, idea, "This idea is closed.", 409)
            except IdeaTextError as error:
                return render_idea(connection, idea, status=400, evidence_form={"kind": "fact"}, evidence_error=error.message)
        finally:
            connection.close()
        return redirect(url_for("idea_detail", token=token) + "#tasting")

    @app.post("/i/<token>/pack")
    def write_starter_pack(token):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            try:
                write_pack(
                    connection,
                    [revision["id"] for revision in idea["branch"]],
                    snapshot(connection, idea),
                    settings(),
                    idea["status"] == "served",
                    chef_transport=app.config.get("CHEF_TRANSPORT"),
                )
            except ChefUnavailable:
                return render_idea(connection, idea, status=503, pack_error="Chef stepped out before writing your starter pack. Try again.")
        finally:
            connection.close()
        return redirect(url_for("idea_detail", token=token) + "#pack")

    @app.get("/i/<token>/starter-pack.md")
    def starter_pack(token):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            stored = latest_of(connection, [revision["id"] for revision in idea["branch"]], "starter_pack")
            logs = evidence_for(connection, idea["id"])
        finally:
            connection.close()
        if stored is None:
            return redirect(url_for("idea_detail", token=token) + "#pack")
        text = render_pack(
            idea["branch"][0]["one_liner"],
            idea["display_name"],
            logs,
            stored["body"],
            stored["body"]["verified"],
            stored["created_at"][:10],
            needed=SERVE_MIN_LOGS,
        )
        return Response(text, mimetype="text/markdown", headers={"Content-Disposition": 'attachment; filename="starter-pack.md"'})

    @app.post("/i/<token>/gate")
    def gate(token):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            if idea["status"] in ("served", "binned"):
                return render_idea(connection, idea, "This idea is closed.", 409)
            try:
                result = run_gate(
                    connection,
                    idea["id"],
                    idea["branch"][-1]["id"],
                    snapshot(connection, idea),
                    settings(),
                    jev_transport=app.config.get("JEV_TRANSPORT"),
                    starter=starter_gate(idea["level"], sessions_for(connection, idea["id"])),
                )
            except GateNotReady:
                return render_idea(connection, idea, "Log at least 3 conversations this session, or a new one since the last try.", 409)
            if result["label"] == "PASSED":
                set_station(connection, idea["id"], "grill")
        finally:
            connection.close()
        return redirect(url_for("idea_detail", token=token) + "#tasting")

    @app.post("/i/<token>/park")
    def park(token):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            try:
                set_status(connection, idea["id"], "parked")
            except IdeaClosed:
                pass
        finally:
            connection.close()
        return redirect(url_for("home"))

    @app.post("/i/<token>/share")
    def share(token):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            set_shared(connection, idea["id"], not idea["shared"])
        finally:
            connection.close()
        return back_to(token)

    @app.post("/i/<token>/delete")
    def delete(token):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            forget(connection, idea["id"], [revision["id"] for revision in idea["revisions"]])
            delete_idea(connection, idea["id"])
        finally:
            connection.close()
        response = redirect(url_for("home"))
        _forget_token(response, token)
        return response

    @app.post("/i/<token>/serve")
    def serve_idea(token):
        connection = connect(app.config["DATABASE"])
        try:
            idea = load(connection, token)
            if idea["status"] in ("served", "binned"):
                return back_to(token)
            branch = idea["branch"]
            try:
                serve(
                    connection,
                    [revision["id"] for revision in branch],
                    snapshot(connection, idea),
                    settings(),
                    chef_transport=app.config.get("CHEF_TRANSPORT"),
                )
            except NotServable:
                return render_idea(
                    connection, idea, "Serving needs a PROVEN verdict and at least 3 logged conversations.", 409
                )
            except ChefUnavailable:
                return render_idea(connection, idea, "Chef stepped out before writing your pitch. Try again.", 503)
            set_status(connection, idea["id"], "served")
            set_station(connection, idea["id"], "takeaway")
        finally:
            connection.close()
        return back_to(token)


def my_tokens():
    return [token for token in request.cookies.get(COOKIE, "").split(".") if token]


def _remember(response, token):
    tokens = [t for t in my_tokens() if t != token] + [token]
    response.set_cookie(COOKIE, ".".join(tokens), max_age=COOKIE_AGE, httponly=True, samesite="Lax")


def _forget_token(response, token):
    tokens = [t for t in my_tokens() if t != token]
    response.set_cookie(COOKIE, ".".join(tokens), max_age=COOKIE_AGE, httponly=True, samesite="Lax")


def _pitch_form(source=None):
    source = source or {}
    return {
        "display_name": source.get("display_name", ""),
        "one_liner": source.get("one_liner", ""),
        "story": source.get("story", ""),
        "tone": source.get("tone", "") or "tough",
        "level": source.get("level", "") or DEFAULT_LEVEL,
        "shared": source.get("shared") == "on",
        "consent": source.get("consent") == "on",
        "pivot": source.get("pivot", ""),
        "pivot_title": source.get("pivot_title", ""),
    }
