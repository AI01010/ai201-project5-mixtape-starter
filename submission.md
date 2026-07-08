# Project 5 Submission — Mixtape Bug Hunt

## AI Usage

_(I will complete this section in Milestone 4, after the bug work is done.)_

<!-- Notes to self for writing this later, so I don't forget what actually happened:
  - I used Claude Code to orient in the codebase: it read every file and helped me write
    an architecture map (architecture.md), which I adapted into the codebase map below.
  - I asked it to verify its own claims against the code instead of trusting summaries —
    it fact-checked the map and corrected several details it originally got wrong.
  - It helped me get the app running on Windows: the README's
    `FLASK_APP=app:create_app flask run` is bash syntax and fails in PowerShell; the
    working command is `flask --app app:create_app run`.
  - Remember to include at least one place where I verified/corrected AI output myself.
-->

## Codebase Map

Mixtape is a Flask JSON API with no frontend and no login — every endpoint takes user IDs
directly in the URL or the request body. Data lives in a local SQLite database that
`seed_data.py` fills with 5 users, 13 songs, 3 playlists, and some listening history.

### Main files and what each one does

- **`app.py`** — the app factory. `create_app()` configures SQLite, registers four
  blueprints (`/songs`, `/playlists`, `/users`, `/feed`), and creates the tables. The
  shared `db = SQLAlchemy()` object lives here, which is why every service does
  `from app import db`.
- **`models.py`** — 7 SQLAlchemy models: `User`, `Tag`, `Song`, `ListeningEvent`,
  `Rating`, `Playlist`, and `Notification`, plus 3 plain association tables:
  `friendships`, `song_tags`, and `playlist_entries`. The `playlist_entries` table is the
  interesting one: besides the two IDs it also stores `position`, `added_by`, and
  `added_at`, so songs in a playlist have an explicit order and a record of who added
  them — it is not just a set. `Rating` has a unique constraint on `(user_id, song_id)`,
  so rating a song twice updates your existing rating instead of adding a second row.
  `User` stores `listening_streak` and `last_listened_at` directly on the user row.
- **`routes/`** — one file per blueprint (`songs.py`, `playlists.py`, `users.py`,
  `feed.py`). The routes are thin: they parse the request, call one service function, and
  turn any `ValueError` the service raises into a 400 or 404 JSON error.
- **`services/`** — all the real logic:
  - `streak_service.py` records listening events and updates the streak stored on the user.
  - `feed_service.py` builds "Friends Listening Now" (recent events only, one most-recent
    song per friend) and the activity feed (last 20 events, no recency filter).
  - `search_service.py` searches songs by title or artist with a case-insensitive `ilike`.
  - `notification_service.py` creates and reads notifications, and also contains the two
    actions that can trigger them: `add_to_playlist` and `rate_song`.
  - `playlist_service.py` creates playlists and returns a playlist's songs ordered by
    their `position` in `playlist_entries`.
- **`seed_data.py`** — drops and recreates everything, then seeds the test data.
- **`tests/`** — pytest suites for streaks, search, and playlists (nothing for the feed or
  notifications). They run against an in-memory SQLite database.

### Data flow — a user listens to a song and their streak updates

`POST /songs/<song_id>/listen` in `routes/songs.py` calls
`streak_service.record_listening_event(user_id, song_id)`. That function inserts a
`ListeningEvent` stamped with the current UTC time, then calls
`update_listening_streak(user, now)`, which compares today's date with the date of the
user's `last_listened_at`: listening the same day changes nothing, listening on a
consecutive day increments the streak, and a skipped day resets it to 1. The result is
written straight onto the `User` row in the same commit.

What surprised me is that `GET /users/<user_id>/streak` does no calculation at all — it
just returns the stored integer. The streak is computed entirely at write time, so
whatever the last listen wrote is what every later read shows.

### Data flow — a friend adds your shared song to a playlist and you get notified

`POST /playlists/<playlist_id>/songs` in `routes/playlists.py` calls
`notification_service.add_to_playlist(playlist_id, song_id, added_by)` — notably in the
notification service, not the playlist service. It validates that the song, the adder,
and the playlist all exist, appends the song to `playlist.songs` if it is not already
there, and then, if the person adding is not the person who originally shared the song,
calls `create_notification()` for the sharer with type `song_added_to_playlist` and a
pre-rendered message string. The sharer sees it through
`GET /users/<user_id>/notifications`, which just reads `Notification` rows newest-first.

### Patterns I noticed

- **Thin routes, fat services.** Routes never contain business logic; services raise
  `ValueError` for anything invalid and routes translate that into an error response. The
  one exception is `GET /users/<id>`, which queries the `User` model directly.
- **Write-time denormalization.** The streak is stored on the user instead of being
  recomputed from `ListeningEvent` history, and notification bodies are pre-rendered
  strings. Reads are cheap, but a wrong write sticks around.
- **Every model serializes itself** with a `to_dict()` method (except `Tag`, whose names
  get inlined into `Song.to_dict()`), and list endpoints wrap results with a `count`.
- **The association tables are raw `db.Table`s, not model classes.** The seed script
  inserts into them directly, and `playlist_service` joins `playlist_entries` in its
  query so it can order by `position` — the plain `Playlist.songs` relationship has no
  way to express that ordering.
- **Everything is UUID strings and UTC timestamps**, but SQLite stores datetimes without
  timezone info, so `streak_service` re-attaches UTC to `last_listened_at` before doing
  date math.

## Root Cause Analyses

<!-- One entry per fixed bug, using this template (all 5 fields required):

### Issue #N — <title>

**How I reproduced it** — ...

**How I found the root cause** — ...

**The root cause** — ...

**My fix** — ...

**Side-effect check** — ...
-->

_(To be written during Milestone 3, one entry per fix.)_

## Git Log

_(Screenshot of `git log --oneline` on `bugfix/mixtape` goes here before submitting.)_
