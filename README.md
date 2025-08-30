# Honbasho

#### Video Demo
[https://youtu.be/nYWznCJVsVM](https://youtu.be/nYWznCJVsVM)

---

## Description
Honbasho is a fantasy, sumo, web-app built with Python, Flask, and SQLite3.

In sumo tournaments (basho), wrestlers (rikishi) are ranked from **Maegashira 17** up to **Maegashira 1**, followed by the san’yaku ranks of **Komusubi, Sekiwake, Ozeki,** and **Yokozuna**.
Tournaments last 15 days, with each rikishi fighting once per day. The winner is the rikishi with the most victories.

Honbasho is a web-based draft game where one to three players draft a slate of rikishi and earn points for every bout their rikishi wins.
Bonus points are awarded when a rank-and-file Maegashira defeats a san’yaku opponent, when a wrestler achieves an 8th win (*kachikoshi*), a 10th win, wins the tournament, or receives a special prize granted at the end of the tournament.

---

## Technology

### Python
I had never used Python before this class but really enjoyed it. I chose Python for this project as a way of reinforcing what I had learned and to continue my Python education. It is a very suitible language for this type of project and did not reflect a trade-off in any non-trivial way.

### SQLite3
I have used a few relational databases and thought SQLite3 was a fine choice for what is really a proof of concept. Although SQLite3
does have limitations in databse size, row limits, concurrancy, etc; my application is unlikely to hit up against any of these limitations.
I will continue to invest in Honbasho and eventually will choose a more scalable and write-friendly database, but SQLite3's use of SQL is portable, so switching to another relational database will be easy. Also, SQLite3 is frictionless for simple applications, so I feel good about the choice.

### Flask
Flask was also new to me. It is very easy to use and seemlessly interoperates with Python, so I decided to stick with it.
The trade off is that Flask is not really suitible for a production application. It is single threaded, has limited asynch
capabilities, and is not very helpful with horizontal scaling. As I continue to work on Honbasho, I will need to replace Flask
with someting else, Quart perhaps.

### Bootstrap
Used for styling and layout.

---

## Implementation
I used the standard Flask application layout with `templates` and `static` subdirectories.

- `app.py` contains the routes.
- Most of the heavy lifting is in `helpers.py` and the `.html` templates.
- `requirements` as required by Flask
- `dbnotes.txt` contains the db schema and some useful queries used during the development and testing

It is important to note that I continued to learn Python as I was coding this project. So sometimes I would
learn a new way of doing something and new code would reflect this learning. I was inconsistent in going back
and changing previous code to reflect the learning. As a result my Python code is inconsistent and really needs
a rewrite.

---

## Functionality

### Admin
- **Players** – Create players, which are names that can participate in draft/games.
- **Change Password** – Provide username, old password, and new password.
- **Logout**
- **Register/Login** – Accessible from the home screen.

### Basho
- **Banzuke** – Before a tournament, the banzuke (official ranking list) is released.
  - Users can select a tournament and view its banzuke.
  - The system pulls data from a public sumo database and persists it for fast, repeated retrieval.
  - Tables of rikishi information and per-tournament ranks are created/updated as a result of fetching Banzuke.

- **Basho Results** – Users can select any previous tournament, pick a day, and view that day’s results: winner, loser, record, and technique.
  - Data comes from the public sumo database.
  - Results are displayed but not persisted.

### Drafts
- **Review Drafts** – View picks from previously created drafts.
- **New Draft** – Select 1–3 players from previously created Players.
  - Each player selects rikishi from rank “buckets”. 1 player each from:
    - Yokozuna–Komusubi
    - Maegashira 1–4
    - Maegashira 5–8
    - Maegashira 9–12
    - Maegashira 13+
    - Wildcard (any non-selected rikishi of any rank)
  - Each player must select one rikishi per group.
  - No rikishi can be selected twice.
  - Results are persisted in the database.

### Results
- **Draft Results** – A user selects a draft and can:
  - View results up to the last tournament day thus far
  - Step through days sequentially to reveal results.
  - See daily scores and cumulative totals.
  - Days results are persisted, draft-results are updated and ceratiain data elements are
  aggregated for faster lookup

#### Scoring System
- **Base Points**
  - 1 point for a win
  - 0 points for a loss

- **Bonus Points**
  - Maegashira (M1–M17) defeating:
    - Komusubi → +1
    - Sekiwake → +2
    - Ozeki → +3
    - Yokozuna → +5
  - Komusubi defeating:
    - Sekiwake → +1
    - Ozeki → +2
    - Yokozuna → +3
  - Sekiwake defeating:
    - Ozeki → +1
    - Yokozuna → +2
  - Ozeki defeating:
    - Yokozuna → +1

- **End of Tournament**
  - +2 points for each Special Prize
  - +10 points for winning the tournament
