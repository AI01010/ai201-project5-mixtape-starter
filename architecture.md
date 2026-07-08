# Mixtape — Architecture / Codebase Map

Mixtape is a small Flask + SQLAlchemy JSON API for a social music app: users share songs,
rate them, build collaborative playlists, follow friends' listening activity, and track
daily listening streaks. There is no frontend and no authentication — every endpoint takes
user IDs explicitly in the URL or request body. Data lives in a local SQLite database
(`mixtape.db`), seeded by `seed_data.py`.

## Layered structure

Every request follows the same three-layer path:

```
HTTP request
   └─> routes/*.py      (Blueprints: parse input, call one service function,
       │                 catch ValueError -> 4xx JSON, format response)
       └─> services/*.py (all business logic and queries)
           └─> models.py (SQLAlchemy models + association tables, to_dict() serializers)
                └─> SQLite (mixtape.db via Flask-SQLAlchemy)
```

The routes are deliberately thin — none of them contain logic beyond input validation and
response shaping. If an endpoint misbehaves, the cause is in the service it delegates to.

## File-by-file map

| File | Responsibility |
|------|----------------|
| `app.py` | App factory (`create_app`). Configures SQLite, registers the four blueprints under `/songs`, `/playlists`, `/users`, `/feed`, and runs `db.create_all()`. The shared `db = SQLAlchemy()` object lives here, which is why services import `from app import db`. |
| `models.py` | 7 model classes — `User`, `Tag`, `Song`, `ListeningEvent`, `Rating`, `Playlist`, `Notification` — plus 3 plain association tables: `friendships`, `song_tags`, `playlist_entries`. Each model has a `to_dict()` used by routes for JSON serialization. |
| `routes/songs.py` | `GET /songs/search`, `GET /songs/<id>`, `POST /songs/<id>/rate`, `POST /songs/<id>/listen`. Delegates to search, notification (ratings live there), and streak services. |
| `routes/playlists.py` | `POST /playlists/`, `GET /playlists/<id>`, `GET /playlists/<id>/songs`, `POST /playlists/<id>/songs`. Delegates to playlist service; adding a song delegates to `notification_service.add_to_playlist`. |
| `routes/users.py` | `GET /users/<id>`, `GET /users/<id>/streak`, `GET /users/<id>/notifications`, `POST /users/notifications/<id>/read`. |
| `routes/feed.py` | `GET /feed/<id>/listening-now`, `GET /feed/<id>/activity`. |
| `services/streak_service.py` | Records `ListeningEvent`s and maintains `User.listening_streak` / `User.last_listened_at`. Streaks are computed **at write time** and stored on the user row — `get_streak` just reads the stored integer. |
| `services/feed_service.py` | "Friends Listening Now" (recency-filtered, deduplicated to one most-recent song per friend, cutoff = `RECENT_THRESHOLD`) and the activity feed (last N events, no recency filter). |
| `services/search_service.py` | Case-insensitive `ilike` search over `Song.title` / `Song.artist`; also `get_song`. |
| `services/notification_service.py` | Creating/reading/marking notifications — **and also** two interaction actions that may trigger them: `add_to_playlist` and `rate_song`. |
| `services/playlist_service.py` | Playlist creation and retrieval; `get_playlist_songs` queries the `playlist_entries` join table directly to order songs by `position`. |
| `seed_data.py` | Drops + recreates all tables, then seeds 5 users (nova, darius, simone, kenji, aaliya) with friendships, 10 tags, 13 songs (3 with no tags, 5 with one tag, 5 with 3 tags), 3 playlists of 7 songs each, listening events (some minutes old, some hours-to-days old), streak state, and one sample `song_added_to_playlist` notification. |
| `tests/` | Pytest suites for streaks, search, and playlists. They use the app factory with an in-memory SQLite DB and encode the *intended* behavior of those services. |

## Data model

- **User** — `username`, `email`, denormalized `listening_streak` (int) and `last_listened_at`
  (datetime). Relationships to shared songs, ratings, listening events, notifications,
  playlists, and a self-referential many-to-many `friends` (via `friendships`; the seed
  inserts both directions, so friendship rows are symmetric).
- **Song** — title/artist/album/genre, `shared_by` (FK to the user who shared it),
  `share_note`. Tags via `song_tags` (`lazy="subquery"`); `to_dict()` inlines tag names.
- **ListeningEvent** — one row per play: `user_id`, `song_id`, `listened_at`. The raw
  material for both feeds and (indirectly) streaks.
- **Rating** — `user_id`, `song_id`, `score` 1–5, with a unique constraint on
  `(user_id, song_id)`; `rate_song` upserts (updates the score on re-rate).
- **Playlist** — name, `created_by`, `is_collaborative`. Songs via `playlist_entries`.
- **Notification** — `user_id` (recipient), `notification_type` (e.g.
  `song_added_to_playlist`), free-text `body`, `read` flag.
- **playlist_entries** (association table) — notably carries **extra columns** beyond the
  two foreign keys: `position` (NOT NULL), `added_by` (NOT NULL), `added_at`. So playlist
  membership is *ordered and attributed*, not just a set.

All primary keys are UUID strings. All timestamps default to `datetime.now(timezone.utc)`,
but SQLite stores them naive — `streak_service` defensively re-attaches UTC with
`replace(tzinfo=timezone.utc)` before doing date math.

## Traced data flows

**1. A user listens to a song (and their streak updates)**
`POST /songs/<song_id>/listen` → `routes/songs.py:listen()` →
`streak_service.record_listening_event(user_id, song_id)` → inserts a `ListeningEvent`
with `listened_at=now`, then calls `update_listening_streak(user, now)`, which compares
`now.date()` against `user.last_listened_at.date()`: same day → no change; consecutive
day → increment; otherwise → reset to 1. One commit covers both the event and the user
row. Reading the streak (`GET /users/<id>/streak` → `get_streak`) returns the stored
integer without recomputing — so a wrong write is visible on every later read.

**2. A friend adds your shared song to a playlist (and you get notified)**
`POST /playlists/<playlist_id>/songs` → `routes/playlists.py:add_song()` →
`notification_service.add_to_playlist(playlist_id, song_id, added_by)` → validates song,
adder, and playlist exist → appends the song to `playlist.songs` if not already present →
if `song.shared_by != added_by`, calls `create_notification(...)` with type
`song_added_to_playlist` and a rendered message body. The sharer sees it via
`GET /users/<id>/notifications` → `get_notifications` (newest first, optional
`unread_only`).

**3. Friends Listening Now**
`GET /feed/<user_id>/listening-now` → `feed_service.get_friends_listening_now(user_id)` →
collects the user's friend IDs → queries `ListeningEvent`s for those friends with
`listened_at >= now - RECENT_THRESHOLD` (a module-level constant), newest first → walks
the results keeping only the first (most recent) event per friend → returns
friend + song + timestamp dicts.

## Conventions and patterns

- **Thin routes, fat services.** Every route parses input, calls exactly one service
  function, and maps `ValueError` to a 400/404 JSON error. Services raise `ValueError`
  for all not-found/invalid cases.
- **Write-time denormalization.** Streaks are stored on `User` and updated when a listen
  is recorded; notification bodies are pre-rendered strings, not references.
- **Serialization via `to_dict()`** on each model; routes return
  `jsonify({...})` wrappers with `count` fields for lists.
- **Association tables are raw `db.Table`s**, not model classes — the seed script and
  `playlist_service` manipulate them with `db.session.execute(insert()/select())`-style
  Core access, while other code uses the ORM relationships layered on top of them.

## Sharp edges to keep in mind

- `Playlist.songs` is a plain `secondary=playlist_entries` relationship, but the join
  table requires `position` and `added_by` (both NOT NULL) — a bare
  `playlist.songs.append(song)` has no way to supply those values. Ordered reads therefore
  bypass the relationship and query the join table directly (`get_playlist_songs`).
- Rating logic (`rate_song`) and playlist-add logic (`add_to_playlist`) live in
  `notification_service.py`, not in a songs/playlist service — the module groups "actions
  that may notify someone" together.
- `song_tags` joins can multiply rows: a `Song` query joined to `song_tags` yields one row
  per matching tag unless deduplicated.
- The streak is only as correct as the last write; there is no recomputation from
  `ListeningEvent` history.
- Start the app with `flask run` and `FLASK_APP=app:create_app` — running `python app.py`
  double-imports `app.py` (once as `__main__`, once as `app` via the models' import) and
  SQLAlchemy errors out.

## Where the five open issues enter the code

| # | Symptom (reported) | Entry endpoint | Service to read |
|---|--------------------|----------------|-----------------|
| 1 | Streak resets on Sundays | `POST /songs/<id>/listen`, `GET /users/<id>/streak` | `streak_service.update_listening_streak` |
| 2 | Yesterday's listens shown as "listening now" | `GET /feed/<id>/listening-now` | `feed_service.get_friends_listening_now` |
| 3 | Duplicate search results for some songs | `GET /songs/search?q=` | `search_service.search_songs` |
| 4 | No notification when a shared song is rated | `POST /songs/<id>/rate` | `notification_service.rate_song` (compare with `add_to_playlist`) |
| 5 | Most recently added playlist song never returned | `GET /playlists/<id>/songs` | `playlist_service.get_playlist_songs` |

The tests in `tests/` encode the intended behavior for issues #1, #3, and #5 — issues #2
and #4 currently have no test coverage.
