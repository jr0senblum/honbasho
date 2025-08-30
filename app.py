import os
from cs50 import SQL
from flask import Flask, jsonify, redirect, render_template, request, session
from flask_session import Session
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, banzuke_helper, fetch_basho_results, fetch_days_results
from helpers import get_basho_data, get_basho_winner, get_non_future_basho, get_players
from helpers import insert_player_data, load_banzuke, login_required, fetch_save_results


# Configure application
app = Flask(__name__)

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///honbasho.db")

@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


# ------------------ Routes  ------------------  #
@app.route("/")
def index():
    """    Start up work: Load any banzuke that has not been loaded."""
    # load any published banzuke
    load_banzuke(db)

    return render_template("project.html")


@app.route("/banzuke")
@app.route("/banzuke/<int:month>/<int:year>")
@login_required
def banzuke(month=None, year=None):
    """
    If no specific basho asked for, supply list of dictionaries of all bashos.
    If month and year supplied, return list of dicts describing the banzuke for
    the selected basho.
    """

    if month == None or year == None:
        bashos = get_basho_data(db, only_loaded=True)
        return render_template("banzuke.html", bashos=bashos)
    else:
        return banzuke_helper(db, year, month)


@app.route("/basho_results", methods=["GET", "POST"])
def basho_results():
     """
        For GET: return list of bashos not in the future.
        For POSTs, pull the results from sumodb.com and pass them to the page.
        Nothing is persisted
     """
     if request.method == "POST":
        data = request.get_json()
        day = data["day"]
        year = data["year"]
        month = data ["month"]
        j = fetch_basho_results(year, month, day)
        return (j)
     else:
        games = get_non_future_basho(db)
        return render_template("basho_results.html", games=games)


@app.route("/basho_winner/<int:basho>")
@login_required
def basho_winner(basho=None):
    """ Return the winner of the bahso as [{"rikishi_id":895}]; or [] if no winner. """

    return get_basho_winner(db, basho)


@app.route("/change_password", methods=["GET", "POST"])
@login_required
def change_password():
    """Register user"""

    if request.method == "POST":
        old_password = request.form.get("old_password")
        new_password = request.form.get("new_password")
        confirmation = request.form.get("confirmation")

        # Ensure password was submitted
        if not old_password:
            return apology("must provide password", 400)

         # Ensure new password and confirmation are there and match
        if not confirmation or not new_password or confirmation != new_password:
            return apology("passwords do not match or are missing", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE id = ?", session["user_id"])

        # Ensure old password was correct
        if not check_password_hash(rows[0]["hash"], request.form.get("old_password")):
            return apology("old password is incorrect", 400)

        db.execute("UPDATE users SET hash = ? WHERE id = ?",
                   generate_password_hash(new_password), session["user_id"])
        session.clear()
        return redirect("/")
    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("change_password.html")



@app.route("/days_results/<int:draft_id>/<int:day>")
@login_required
def days_results(draft_id=None, day=None):
    """
    Return a list of dictionaries representing the days results with respect
    to a specific draft.
    """

    picks = db.execute("""
        SELECT
            dr.*,
            r.ring_name,
            rw.rank_no  AS winner_rank_no,
            ro.rank_no  AS opponent_rank_no
        FROM days_results AS dr
        JOIN rikishi  AS r  ON dr.rikishi_id = r.id
        JOIN drafts   AS d  ON d.id = dr.draft_id
        -- winner rank
        JOIN banzuke  AS bw ON bw.basho_id = d.basho_id AND bw.rikishi_id  = dr.rikishi_id
        JOIN ranks    AS rw ON rw.id = bw.rank_id
        -- opponent rank
        JOIN banzuke  AS bo ON bo.basho_id = d.basho_id AND bo.rikishi_id  = dr.oponent_id
        JOIN ranks    AS ro ON ro.id = bo.rank_id
        WHERE dr.draft_id = ? AND dr.tournament_day = ?
        """, draft_id, day)
    if picks:
        current = db.execute("SELECT last_seen FROM drafts WHERE id = ?", draft_id )
        if day > current[0]['last_seen']:
            db.execute("UPDATE drafts SET last_seen = ? WHERE id = ?", day, draft_id)

        return picks
    else:
        return []


@app.route("/delete_draft/<int:draft_id>", methods=["DELETE"])
def delete_draft(draft_id):
    """
    Delete the draft with the given id: delete from draft_picks and draft tables.
    :param draft_id: the id of the draft to be deleted

    """

    days_results=db.execute("SELECT * FROM days_results WHERE draft_id = ? LIMIT 1", draft_id)
    if days_results:
        # if we aleady have scores, we should not allow the draft to be delted
        return jsonify(ok=False, code="Draft has results and cannot be deleted."), 409

    user = db.execute("SELECT user_id FROM drafts WHERE id = ?", draft_id)
    if user[0]['user_id'] != session["user_id"]:
        return jsonify(ok=False, code="Draft does not belong to you so cannot be deleted."), 403

    db.execute("DELETE FROM draft_picks WHERE draft_id = ?", draft_id)
    db.execute("DELETE FROM drafts WHERE id = ?", draft_id)

    return jsonify(ok=True), 204


@app.route("/drafts")
def drafts():
    """"
    Return a list of all drafts
    """
    user_id = session["user_id"]
    user_id = session["user_id"]
    drafts = db.execute("""
        SELECT
          d.id          AS draft_id,
          d.name        AS draft_name,
          d.basho_id    AS basho_id,
          b.city        AS city,
          b.start_year  AS start_year,
          b.start_month AS start_month
        FROM drafts d
        JOIN basho  b ON b.id = d.basho_id
        WHERE d.user_id = ?
        ORDER BY b.start_year DESC, b.start_month DESC, d.id DESC
    """, user_id)

    return render_template("drafts.html", drafts = drafts)



@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 400)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]
        session["user_name"] = rows[0]["username"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")




# Create a new draft
@app.route("/new_draft", methods=["GET", "POST"])
def new_draft():
    """
    Create a new draft.
    GET rturns a list of all Bashos with banzukes so user can drat.
    POST gathers draft and persists it.
    """

    user_id = session["user_id"]

    if request.method == "POST":
        data = request.get_json()
        players = data["players"]
        basho_id = data["basho_id"]
        draft_name = (data["draft_name"]).strip()

        exists = db.execute("SELECT 1 FROM drafts WHERE user_id = ? AND basho_id = ? AND name = ?", user_id, basho_id, draft_name)
        if exists:
            return jsonify(ok=False, code="DUPLICATE_NAME",
                           message="A draft with this name already exists. Choose a unique name."), 409

        db.execute("INSERT INTO drafts "
                   "       (user_id, basho_id, name) "
                   "       VALUES (?, ?, ?) ",
                   user_id, basho_id, draft_name)
        draft_id = db.execute("SELECT last_insert_rowid()")[0]["last_insert_rowid()"]

        for slate in players:
            player_id = slate["player_id"]
            picks = slate["picks"]
            for pick in picks.values():
                rikishi_id = pick["id"]
                db.execute("INSERT INTO draft_picks "
                           "(draft_id, player_id, rikishi_id) VALUES(?, ?, ?)",
                           draft_id, player_id, rikishi_id)
        return jsonify(ok=True, draft_id=draft_id), 201
    else:
        # GET list of basho
        basho = db.execute("SELECT * "
                           "FROM basho WHERE banzuke_loaded = 1 "
                           "ORDER BY start_year, start_month DESC ")
        players = get_players(db, session["user_id"])
        drafts = db.execute("SELECT * FROM drafts WHERE user_id = ?", user_id)
        return render_template("new_draft.html", players = players, basho=basho, drafts=drafts)


@app.route("/parse_sumodb_day/<int:year>/<int:month>/<int:day>")
def parse_sumdb_day_ep(year, month, day):
    return (fetch_basho_results(year, month, day))


@app.route("/picks/<int:draft_id>")
@login_required
def oldpicks(draft_id=None):
    picks = db.execute("SELECT draft_picks.draft_id, "
                       "       draft_picks.player_id, "
                       "       rikishi.id as rikishi_id, "
                       "       rikishi.ring_name, "
                       "       players.name as player_name, "
                       "       drafts.basho_id, "
                       "       basho.start_year, "
                       "       basho.start_month "
                      "  FROM draft_picks "
                      "  JOIN players ON player_id = players.id "
                      "  JOIN rikishi ON draft_picks.rikishi_id = rikishi.id "
                      "  JOIN drafts  ON drafts.id = draft_picks.draft_id "
                      "  JOIN basho   ON basho.id  = drafts.basho_id "
                      " WHERE draft_id = ?",
                      draft_id)
    last_seen = db.execute("SELECT last_seen FROM drafts WHERE id = ?", draft_id )

    return {'picks':picks, 'last_seen': last_seen[0]['last_seen']}


@app.route("/players", methods=["GET", "POST"])
@login_required
def players():
    if request.method == "GET":
        players = get_players(db, session["user_id"])
        return render_template("players.html", players=players, username=session["user_name"])
    else:
        name = request.form["name"]
        insert_player_data(db, name, user_id = session["user_id"])
        return redirect("/players")



@app.route("/prize_winners/<int:basho>")
@login_required
def prize_winners(basho=None):
    return db.execute("SELECT rikishi_id FROM draft_picks JOIN drafts ON draft_id = drafts.id WHERE special_prizes <> 0 AND basho_id = ?", basho)



@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")
        confirmation = request.form.get("confirmation")
        # Ensure username was submitted
        if not username:
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not password:
            return apology("must provide password", 400)

        elif not confirmation or confirmation != password:
            return apology("passwords do not match", 400)
        try:
            db.execute("INSERT INTO users (username, hash) VALUES (?, ?)",
                       username, generate_password_hash(password))
        except ValueError:
            return apology("username already exists", 400)
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")



@app.route("/score_game", methods=["GET", "POST"])
@login_required
def score_game():
    """
    Ensure that
    """

    bashos = get_basho_data(db, only_loaded = True)
    for basho in bashos:
        fetch_save_results(db, session["user_id"], basho['id'])

    if request.method == "GET":
        games = db.execute("SELECT drafts.id as draft_id, "
                           "       drafts.name AS draft_name, "
                           "       basho.id, "
                           "       basho.name, "
                           "       basho.city, "
                           "       basho.last_update_day, "
                           "       start_month, "
                           "       start_day, "
                           "       start_year "
                           "  FROM basho "
                           "  JOIN drafts ON basho.id = drafts.basho_id"
                           " WHERE  drafts.user_id = ?",
                           session["user_id"])
        return render_template("score_game.html", games=games)
    else:
        draft_id = request.form["draft_id"]
        results = db.execute("SELECT * "
                             "  FROM days_results "
                             "  JOIN rikishi ON days_results.rikishi_id=rikishi.id "
                             " WHERE draft_id = ? "
                             " ORDER BY tournament_day ASC",
                             draft_id)
        return results
