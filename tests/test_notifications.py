"""
tests/test_notifications.py — Mixtape

Regression tests for rating notifications (Issue #4).
"""

import pytest
from app import create_app, db
from models import User, Song
from services.notification_service import rate_song, get_notifications


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def shared_song(app):
    """A sharer, a friend who will rate, and the sharer's song."""
    with app.app_context():
        sharer = User(username="sharer", email="sharer@example.com")
        rater = User(username="rater", email="rater@example.com")
        db.session.add_all([sharer, rater])
        db.session.flush()

        song = Song(title="Shared Song", artist="Various", shared_by=sharer.id)
        db.session.add(song)
        db.session.commit()
        yield {"sharer": sharer, "rater": rater, "song": song}


def test_rating_notifies_the_sharer(app, shared_song):
    """
    Rating someone else's shared song creates a notification for the sharer.

    Regression test for Issue #4: the rating was saved but no notification
    was ever created.
    """
    with app.app_context():
        rate_song(shared_song["rater"].id, shared_song["song"].id, 5)

        notifs = get_notifications(shared_song["sharer"].id)
        assert any(n["type"] == "song_rated" for n in notifs)  # Bug: no notification at all


def test_rating_your_own_song_does_not_notify(app, shared_song):
    """Rating your own shared song should not notify yourself."""
    with app.app_context():
        rate_song(shared_song["sharer"].id, shared_song["song"].id, 4)

        notifs = get_notifications(shared_song["sharer"].id)
        assert notifs == []


def test_rating_is_still_saved(app, shared_song):
    """The rating itself persists with the given score."""
    with app.app_context():
        rating = rate_song(shared_song["rater"].id, shared_song["song"].id, 3)
        assert rating.score == 3
