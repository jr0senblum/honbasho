import re
import requests
from bs4 import BeautifulSoup
from flask import redirect, render_template, session
from functools import wraps
from datetime import date

def apology(message, code=400):
    """Render message as an apology to user."""

    def escape(s):
        """
        Escape special characters.

        https://github.com/jacebrowning/memegen#special-characters
        """
        for old, new in [
            ("-", "--"),
            (" ", "-"),
            ("_", "__"),
            ("?", "~q"),
            ("%", "~p"),
            ("#", "~h"),
            ("/", "~s"),
            ('"', "''"),
        ]:
            s = s.replace(old, new)
        return s

    return render_template("apology.html", top=code, bottom=escape(message)), code

def login_required(f):
    """
    Decorate routes to require login.

    https://flask.palletsprojects.com/en/latest/patterns/viewdecorators/
    """

    @wraps(f)
    def decorated_function(*args, **kwargs):
        if session.get("user_id") is None:
            return redirect("/login")
        return f(*args, **kwargs)

    return decorated_function




# Build {1: [{'EAST': {'Name': 'jhn', 'ID': 10}, 'rank_name': 'Yokozuna', 'WEST': {'Name': 'whe', 'ID': 11}]
def banzuke_helper(db, year:int, month:int):
    """
    Create a data structure of the banzuke for an html page to render
    """

    fighters = db.execute("SELECT ring_name, rikishi_id, rank_no, rank_name, cardinality FROM banzuke "
                          "JOIN basho ON basho_id=basho.id "
                          "JOIN rikishi ON rikishi_id=rikishi.id "
                          "JOIN ranks ON rank_id=ranks.id "
                          "WHERE basho.start_month = ? AND basho.start_year = ? AND "
                          "      banzuke.call_up = 0 "
                          "ORDER BY rank_no ASC", month, year)

    ranked = {}

    for fighter in fighters:
        ring_name = fighter["ring_name"]
        rikishi_id = fighter["rikishi_id"]
        rank_no = fighter["rank_no"]
        rank_name = fighter["rank_name"]
        cardinality = fighter["cardinality"]

        # Ensure the rank key exists
        if rank_no not in ranked:
            ranked[rank_no] = [{"EAST": {"name": "--", "id": "--"},
                                "rank_name": rank_name,
                                "WEST": {"name": "--", "id": "--"}}]


        # Try to place the fighter in an existing slot
        placed = False
        for slot in ranked[rank_no]:
            if slot[cardinality]["name"] == "--":
                slot[cardinality]["name"] = ring_name
                slot[cardinality]["id"] = rikishi_id
                placed = True
                break

        # If no empty slot was found, start a new East/West pair
        if not placed:
            if cardinality == "EAST":
                ranked[rank_no].append({"EAST": {"name": ring_name, "id": rikishi_id}, "rank_name": rank_name, "WEST": {"name": "--", "id": "--"}})
            else:
                ranked[rank_no].append({"EAST": {"name": "--", "id": "--"}, "rank_name": rank_name, "WEST": {"name": ring_name, "id": rikishi_id}})
    return ranked






def fetch_basho_results(year:int, month:int, day:int):
    """
    Fetch and parse the N-th day results from sumodb.sumogames.de
    :param year: basho year e.g. "2025"
    :param month: basho month
    :param day: day number
    :return: dict with basho, day and list of bouts:
      [{winner, winner_record, loser, loser_record, technique}, …]
    """
    url = f"https://sumodb.sumogames.de/results.aspx?b={year}{month:02d}&d={day}"
    resp = requests.get(url)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.find("table", class_="tk_table")
    if not table:
        raise RuntimeError(f"Couldn't find the results table for basho={basho_ym}, day={day}")

    bouts = []
    for tr in table.find_all("tr"):
        tds = tr.find_all("td")
        if len(tds) != 5:
            continue

        left_star  = tds[0].find("img")["src"]
        right_star = tds[4].find("img")["src"]

        # decide which side won
        win_images = ("hoshi_shiro.gif", "hoshi_fusensho.gif")
        if any(img in left_star  for img in win_images):
            winner_td, loser_td = tds[1], tds[3]
        elif any(img in right_star for img in win_images):
            winner_td, loser_td = tds[3], tds[1]
        else:
            # no clear winner marker → skip
            continue

        # technique override for fusen‐wins/dropouts
        if "fusen" in left_star or "fusen" in right_star:
            technique = "fusen"
        else:
            tech_strings = list(tds[2].stripped_strings)
            technique = next((s for s in tech_strings if s.isalpha()), "")

        # helper to extract name + record and strip off the "(...)"
        def extract_info(cell):
            name = cell.find(
                "a", href=lambda u: u and u.startswith("Rikishi.aspx")
            ).get_text(strip=True)
            raw_rec = cell.find(
                "a", href=lambda u: u and "Rikishi_basho.aspx" in u
            ).get_text(strip=True)
            rec = re.sub(r'\s*\(.*?\)', '', raw_rec)
            return name, rec

        winner_name, winner_record = extract_info(winner_td)
        loser_name,  loser_record  = extract_info(loser_td)

        bouts.append({
            "winner":        winner_name,
            "winner_record": winner_record,
            "loser":         loser_name,
            "loser_record":  loser_record,
            "technique":     technique
        })


    return bouts

# return the rikishi's id or None if it does not exist
def get_rikishi_id(db, name):
    result = db.execute("SELECT id FROM rikishi where ring_name = ?", name)
    return result[0]['id'] if result else None


# if Rikishi isn't in table add it, even if it is, it might not be in the banzuke, so add there as well.
# call_up indicates a rikishi who was pulled up temporarily due to drop outs
def add_if_missing_rikishi(db, basho_id, ring_name, rank, call_up=False):

    rikishi_id = get_rikishi_id(db, ring_name)
    if rikishi_id is not None:
        q = db.execute("SELECT id FROM banzuke WHERE rikishi_id = ? AND basho_id = ?", rikishi_id, basho_id)
        if not q:
            db.execute("INSERT INTO banzuke (basho_id, rikishi_id, call_up, rank_id) VALUES (?, ?, ?, ?)",
                       basho_id, rikishi_id, call_up==True, rank)
    else:
        q = db.execute("INSERT INTO rikishi (ring_name) VALUES (?)", ring_name)
        rikishi_id = db.execute("SELECT last_insert_rowid()")[0]["last_insert_rowid()"]
        db.execute("INSERT INTO banzuke (basho_id, rikishi_id, call_up, rank_id) VALUES (?, ?, ?, ?)", basho_id, rikishi_id, call_up==True, rank)

    return rikishi_id


# given JSON {winner: _, winner_record: _, loser: loser_, loser_record: _, tecnique: _}, add
# the rank of each fighter. i.e., add winner_rank: _, looser_rank: _, winner_id: _, looser_id: _
def amend_results(db, basho_id, bouts):
    def get_rikishi_info(ring_name):
        q = db.execute("""
            SELECT rikishi.id AS rikishi_id, rank_no
            FROM   banzuke
            JOIN   rikishi ON banzuke.rikishi_id = rikishi.id
            JOIN   ranks ON banzuke.rank_id = ranks.id
            WHERE  ring_name = ? AND banzuke.basho_id = ? """,
            ring_name, basho_id)
        if not q:
            # should not happen because called after add_if_missing
            raise ValueError(f"Rikishi {ring_name} not found in banzuke for basho {basho_id}")
        return q[0]['rikishi_id'], q[0]['rank_no']

    for bout in bouts:
        add_if_missing_rikishi(db, basho_id, bout['winner'], 44, True)
        add_if_missing_rikishi(db, basho_id, bout['loser'], 44, True)

        bout['winner_id'], bout['winner_rank'] = get_rikishi_info(bout['winner'])
        bout['loser_id'],  bout['loser_rank']  = get_rikishi_info(bout['loser'])

    return bouts


# given {winner: _, winner_record: _, loser: loser_, loser_record: _, tecnique: _, winner_rank: _, looser_rank: _, winner_id: _, looser_id: _}
# add win_points:_
# This is the first time we care about a particular draft
def calculate_points_fast(db, draft_id, bouts):
    """
    Input 'bouts' from amend_results(), which includes:
      winner_id, loser_id, winner_rank, loser_rank, technique
    Output adds: win_points (int)
    Only winners' points change; losers get 0 (as in your original).
    """

    # 1) Gather all winner_ids we might care about
    winner_ids = {b["winner_id"] for b in bouts}

    if not winner_ids:
        for b in bouts:
            b["win_points"] = 0
        return bouts

    # 2) Load current wins for all those rikishi in ONE query
    placeholders = ",".join("?" for _ in winner_ids)
    rows = db.execute(
        f"SELECT rikishi_id, wins FROM draft_picks "
        f"WHERE draft_id = ? AND rikishi_id IN ({placeholders})",
        draft_id, *winner_ids
    )
    wins_by_id = {r["rikishi_id"]: r["wins"] for r in rows}

    def compute_kicker(winner_rank, loser_rank, technique, current_wins):
        kicker = 0
        # thresholds based on current_wins BEFORE this bout
        if current_wins == 7:  # kachikoshi on this win
            kicker += 2
        elif current_wins == 9:  # 10th win on this win
            kicker += 1

        if technique != "fusen":
            if winner_rank > 4:  # M ranks
                if loser_rank == 4: kicker += 1   # beat Komusubi
                elif loser_rank == 3: kicker += 2 # beat Sekiwake
                elif loser_rank == 2: kicker += 3 # beat Ozeki
                elif loser_rank == 1: kicker += 5 # beat Yokozuna
            elif winner_rank == 4:  # K
                if loser_rank == 3: kicker += 1
                elif loser_rank == 2: kicker += 2
                elif loser_rank == 1: kicker += 3
            elif winner_rank == 3:  # S
                if loser_rank == 2: kicker += 1
                elif loser_rank == 1: kicker += 2
            elif winner_rank == 2:  # O
                if loser_rank == 1: kicker += 1

        return kicker

    # 3) Annotate bouts
    for b in bouts:
        cur_wins = wins_by_id.get(b["winner_id"], 0)
        b["win_points"] = compute_kicker(
            b["winner_rank"], b["loser_rank"], b["technique"], cur_wins
        )

    return bouts



# given {winner: _, winner_record: _, loser: loser_, loser_record: _, tecnique: _,
#        winner_rank: _, looser_rank: _,  winner_id: _, looser_id: _, win_points:_}
# update the days_results table
def update_results_fast(db, draft_id, tournament_day, bouts):
    # 1) Limit to rikishi that were actually drafted in THIS draft
    ids = {b["winner_id"] for b in bouts} | {b["loser_id"] for b in bouts}
    if not ids:
        return
    ph = ",".join("?" for _ in ids)
    rows = db.execute(
        f"SELECT rikishi_id FROM draft_picks WHERE draft_id = ? AND rikishi_id IN ({ph})",
        draft_id, *ids
    )
    valid = {r["rikishi_id"] for r in rows}
    if not valid:
        return

    insert_sql = """
        INSERT OR IGNORE INTO days_results
          (draft_id, tournament_day, rikishi_id, oponent_id, win, loss, funsensho, points)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """

    # 2) Apply winners
    for b in bouts:
        if b["winner_id"] in valid:
            is_fusen = 1 if b["technique"] == "fusen" else 0
            pts = b["win_points"] + 1
            db.execute(
                insert_sql,
                draft_id, tournament_day, b["winner_id"], b["loser_id"],
                1, 0, is_fusen, pts
            )
            # increment counters (safe even if INSERT was ignored once per unique constraint)
            db.execute(
                "UPDATE draft_picks SET wins = wins + 1, points = points + ? "
                "WHERE draft_id = ? AND rikishi_id = ?",
                pts, draft_id, b["winner_id"]
            )

    # 3) Apply losers
    for b in bouts:
        if b["loser_id"] in valid:
            is_fusen = 1 if b["technique"] == "fusen" else 0
            db.execute(
                insert_sql,
                draft_id, tournament_day, b["loser_id"], b["winner_id"],
                0, 1, is_fusen, 0
            )
            db.execute(
                "UPDATE draft_picks SET losses = losses + 1 "
                "WHERE draft_id = ? AND rikishi_id = ?",
                draft_id, b["loser_id"]
            )



def fetch_sansho_winners(db, draft_id, year: int, month: int):
    """
    Fetch Sanshō winners for a given basho (year, month) from sumodb.
    Returns a list of dicts: [{ "prize": ..., "ring_name": ... }, ...]
    """
    url = "https://sumodb.sumogames.de/Sansho.aspx"
    target = f"{year}.{month:02d}"

    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    table = soup.find("table")
    if not table:
        raise RuntimeError("No table found on page")

    rows = table.find_all("tr")
    target_row = None
    for row in rows[1:]:  # skip header
        cells = row.find_all("td")
        if not cells:
            continue
        if cells[0].text.strip() == target:
            target_row = cells
            break

    if not target_row:
        raise ValueError(f"No basho found for {target}")

    prize_names = ["Gino‑sho", "Shukun‑sho", "Kanto‑sho"]
    results = []

    for idx, prize in enumerate(prize_names, start=1):
        td = target_row[idx]
        if not td or not td.text.strip() or "not awarded" in td.text.lower():
            continue

        for a in td.find_all("a"):
            full_text = a.text.strip()
            # Strip rank prefix like "M14e Kusano"
            parts = full_text.split()
            ring_name = parts[-1] if len(parts) >= 2 else full_text
            results.append({
                "prize": prize,
                "ring_name": ring_name
            })

    if results:
        # prizes have now been fetched
        db.execute("UPDATE drafts SET prizes = 1 WHERE id = ?", draft_id)

    for prize in results:
        id = get_rikishi_id(db, prize['ring_name'])
        db.execute("UPDATE draft_picks "
                   "   SET special_prizes = special_prizes + 1, "
                   "       points = points + 2 "
                   " WHERE draft_id = ? AND rikishi_id = ?",
                   draft_id,
                   id)

    return results

def fetch_makuuchi_yusho_winner(db, draft_id, year: int, month: int):
    basho_ym = f"{year}{month:02d}"
    url = f"https://sumodb.sumogames.de/Results_text.aspx?b={basho_ym}"

    resp = requests.get(url)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    pre = soup.find("pre")
    if not pre:
        raise RuntimeError("Could not find results text block")

    lines = pre.get_text().splitlines()

    in_makuuchi = False
    most_wins = -1
    winner = None

    for line in lines:
        line = line.strip()
        if line == "Makuuchi":
            in_makuuchi = True
            continue
        elif in_makuuchi and re.match(r"^[A-Z][a-z]", line):  # e.g. "Juryo"
            break
        elif in_makuuchi:
            parts = re.split(r"\s{2,}", line)
            for i in [1, 4]:  # these are the ring name + record columns
                if i < len(parts):
                    part = parts[i]
                    if "(" in part and ")" in part:
                        try:
                            ring_name = part.split(" (")[0]
                            record = part.split("(")[1].split(")")[0]
                            wins = int(record.split("-")[0])
                            if wins > most_wins:
                                most_wins = wins
                                winner = ring_name
                        except Exception:
                            continue

    if not winner:
        return {"winner": "None"}

    id = get_rikishi_id(db, winner)
    db.execute("UPDATE draft_picks "
               "   SET basho_winner = 1, "
               "       points = points + 10 "
               " WHERE draft_id = ? AND rikishi_id = ?",
                   draft_id,
                   id)
    if winner:
        # winner has been fetched
        db.execute("UPDATE drafts SET winner = 1 WHERE id = ?", draft_id)

    return {"winner": winner}






# Return number of rows impacted by sql, help stop loosing race conditions
def cas_update(db, sql, *params):
    db.execute(sql, *params)
    # SQLite rowcount via changes()
    n = db.execute("SELECT changes() AS n")[0]["n"]
    return n


def fetch_days_results(db, basho_id, user_id, day):
    """
    Fetch the result for the day-th day of the basho (if not already fetched)
    Update the days_results for the given user's drafts if not already done
    """
    if not (1 <= day <= 16):
        return None

    game_details = db.execute("SELECT id as draft_id, last_days_results_loaded "
                              "  FROM drafts "
                              " WHERE user_id = ? AND basho_id = ? "
                              " LIMIT 1",
                              user_id,
                              basho_id)

    # Update basho.last_update_day if no one else has
    cas_update(db, "UPDATE basho SET last_update_day = ? WHERE id = ? AND last_update_day = ?",
              day,
              basho_id,
              day - 1)

    basho_details = db.execute("SELECT start_year, start_month "
                               "FROM basho "
                               "WHERE id = ?",
                               basho_id)

    year = basho_details[0]['start_year']
    month = basho_details[0]['start_month']
    draft_id = game_details[0]['draft_id']
    max_day = game_details[0]["last_days_results_loaded"]

    if max_day != day - 1:
         return None

    results = fetch_basho_results(year, month, day)
    amended = amend_results(db, basho_id, results)
    points = calculate_points_fast(db, draft_id, amended)

    # ---- All writes IN ONE TRANSACTION ----
    db.execute("BEGIN")
    try:
        update_results_fast(db, draft_id, day, points)        # see F)
        # Mark the draft as having loaded this day; CAS to be safe if concurrent
        cas_update(
            db,
            "UPDATE drafts SET last_days_results_loaded = ? WHERE id = ? AND last_days_results_loaded = ?",
            day, draft_id, day - 1
        )
        db.execute("COMMIT")
    except Exception:
        db.execute("ROLLBACK")
        raise


def insert_player_data(db, name, user_name=None, user_id=None):
    """
    Insert a player into the players table associated with the user
    Parameters:
     db   -- database connection
     name -- player name
     user_name -- optional name of the associated user
     user_id -- optional id of the associated user
    One of user_name or user_id must be supplied.
    """
    def resolve_user_id():
        if user_id is not None:
            result = db.execute("SELECT id FROM users WHERE id = ?", user_id)
            if result:
                return result[0]['id']
        elif user_name:
            result = db.execute("SELECT id FROM users WHERE username = ?", user_name)
            if result:
                return result[0]['id']
        return None

    resolved_id = resolve_user_id()
    if resolved_id is None:
        return None

    exists = db.execute("SELECT * FROM players WHERE user_id = ? and name = ?", resolved_id, name)
    if exists:
        return None

    db.execute("INSERT INTO players (name, user_id) VALUES (?, ?)", name, resolved_id)
    player_id = db.execute("SELECT last_insert_rowid()")[0]["last_insert_rowid()"]
    return player_id

def get_players(db, id):
    return db.execute("SELECT * FROM players WHERE user_id = ?", id)




# Feth a banzuke for the year/month from sumodb
def c_to_rank(c):
    special_ranks = {'Y': 1, 'O': 2, 'S': 3, 'K': 4}
    if c in special_ranks:
        return special_ranks[c]
    return int(c[1:]) + 4


def fetch_banzuke(year:int, month:int):
    """
    Fetch the Makuuchi banzuke for a given month/year from sumodb.sumogames.de
    and return JSON with each wrestler's name, rank, and East/West side.
    """
    # build the YYYYMM parameter
    basho_ym = f"{year}{int(month):02d}"
    url = f"https://sumodb.sumogames.de/Banzuke.aspx?b={basho_ym}"
    resp = requests.get(url)
    resp.raise_for_status()

    soup = BeautifulSoup(resp.text, "html.parser")
    # find the banzuke table whose caption says "Makuuchi Banzuke"
    makuuchi_table = None
    for tbl in soup.find_all("table", class_="banzuke"):
        cap = tbl.find("caption")
        if cap and "Makuuchi Banzuke" in cap.get_text():
            makuuchi_table = tbl
            break
    if makuuchi_table is None:
        #raise RuntimeError(f"Could not find Makuuchi banzuke for {basho_ym}")
        return []

    results = []
    for tr in makuuchi_table.tbody.find_all("tr"):
        # the rank cell in every row
        rank_td = tr.find("td", class_="short_rank")
        if not rank_td:
            continue
        rank = c_to_rank(rank_td.get_text(strip=True))

        # grab *any* cell with a link to Rikishi.aspx (skips the record‑links,
        # because those point to Rikishi_basho.aspx, not Rikishi.aspx)
        rikishi_tds = [
            td for td in tr.find_all("td")
            if td.find("a", href=lambda u: u and u.startswith("Rikishi.aspx"))
        ]

        for td in rikishi_tds:
            name = td.find("a", href=lambda u: u and u.startswith("Rikishi.aspx")).get_text(strip=True)
            # East if it's to the left of the rank cell; otherwise West
            side = "East" if tr.find_all("td").index(td) < tr.find_all("td").index(rank_td) else "West"
            results.append({
                "name": name,
                "rank": rank,
                "side": side
            })

    return results



def persist_banzuke(db, basho_id, year:int, month:int) -> None:
    """
    Fetch the baanzuzke from sumodb via helper function, and persist to database.
    :param db: database connection
    :param basho_id: id of the basho
    :param year: basho year e.g. "2025"
    :param month: basho month
    """

    try:
        banzuke = fetch_banzuke(year, month)
        if not banzuke:
            return None
    except RuntimeError:
        raise RuntimeError("Failed to fetch banzuke data from sumodb.")

    # Add each rikishi to the rikishi table and to the banzuke table for the given basho
    for rikishi in banzuke:
        ring_name = rikishi['name']
        side = rikishi['side'].upper()
        rank = rikishi['rank']
        q_ranks = db.execute("SELECT id FROM ranks WHERE rank_no = ? AND cardinality = ?", rank, side)
        rank_id = q_ranks[0]['id']

        # helper function adds to rikishi table and banzuke table
        add_if_missing_rikishi(db, basho_id, ring_name, rank_id, False)

    db.execute("UPDATE basho SET banzuke_loaded = 1 WHERE id = ?", basho_id)


def get_basho_data(db, only_loaded=False):
    """
    Return all this year-to-date's basho (i.e., start_month <= this month and
    start_year = this year).
    :param db: database connection
    :param only_loaded is True if you only want the ones with banzuke, else false
    """

    current_year = date.today().year
    current_month = date.today().month
    basho = db.execute("SELECT * "
                       "  FROM basho "
                       " WHERE banzuke_loaded = ? AND start_year = ? and start_month <= ? ",
                       only_loaded == True,
                       current_year,
                       current_month)

    return basho


def load_banzuke(db):
    """
    Fetch banzuke for all bashos that are  or have happened this  and not already loaded
    :param db: database connection
    """

    basho = get_basho_data(db, only_loaded = False)
    for b in basho:
        persist_banzuke(db, b['id'], b['start_year'], b['start_month'])


def fetch_save_results(db, user_id, basho_id):
    """
    Get results for the given basho.
    Store results in days_results table
    """

    today = date.today()

    bashos = db.execute("SELECT basho.id as basho_id, last_update_day, start_year, start_month, start_day, drafts.id as draft_id "
                        "  FROM basho "
                        "  JOIN drafts ON basho.id = drafts.basho_id "
                        " WHERE basho.id = ? AND last_update_day < 16 ",
                        basho_id)

    for basho in bashos:
        start_day = basho['start_day']
        start_month = basho['start_month']
        start_year = basho['start_year']
        last_update_day = basho['last_update_day']

        target_date = date(today.year, start_month, start_day)
        days_between = min(16, abs((target_date - today).days))


        for i in range(last_update_day, days_between + 1):
            fetch_days_results(db, basho['basho_id'], user_id, i)

            if i == 15:
                fetch_sansho_winners(db, basho['draft_id'], start_year, start_month)
                fetch_makuuchi_yusho_winner(db, basho['draft_id'], start_year, start_month)

def get_basho_winner(db, basho_id):
    return db.execute("SELECT rikishi_id "
                      "  FROM draft_picks "
                      "  JOIN drafts ON draft_id = drafts.id "
                      " WHERE basho_winner == 1 AND basho_id = ?",
                      basho_id)

def get_non_future_basho(db):
    """
    Return all basho that are not in the future.
    """

    query = db.execute("SELECT basho.id as basho_id, "
                       "       basho.name, "
                       "       basho.city, "
                       "       start_month, "
                       "       start_day, "
                       "       start_year "
                       "  FROM basho "
                       " WHERE date(printf('%04d-%02d-%02d', start_year, start_month, start_day)) < date('now')")
    return query

