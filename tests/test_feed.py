"""
tests/test_feed.py — Mixtape

Regression tests for the "Friends Listening Now" feed (Issue #2).
"""

import pytest
from datetime import datetime, timedelta, timezone
from app import create_app, db
from models import User, Song, ListeningEvent, friendships
from services.feed_service import get_friends_listening_now


@pytest.fixture
def app():
    app = create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:"})
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()


@pytest.fixture
def friends(app):
    """Two users who are friends, plus a song for the friend to listen to."""
    with app.app_context():
        viewer = User(username="viewer", email="viewer@example.com")
        friend = User(username="friend", email="friend@example.com")
        db.session.add_all([viewer, friend])
        db.session.flush()

        song = Song(title="Test Track", artist="Various", shared_by=viewer.id)
        db.session.add(song)
        db.session.flush()

        db.session.execute(friendships.insert().values(user_id=viewer.id, friend_id=friend.id))
        db.session.execute(friendships.insert().values(user_id=friend.id, friend_id=viewer.id))
        db.session.commit()
        yield {"viewer": viewer, "friend": friend, "song": song}


def test_friend_who_listened_today_appears(app, friends):
    """A friend who listened earlier today shows up in the feed."""
    with app.app_context():
        just_after_midnight = datetime.now(timezone.utc).replace(
            hour=0, minute=1, second=0, microsecond=0
        )
        db.session.add(ListeningEvent(
            user_id=friends["friend"].id,
            song_id=friends["song"].id,
            listened_at=just_after_midnight,
        ))
        db.session.commit()

        feed = get_friends_listening_now(friends["viewer"].id)
        assert len(feed) == 1
        assert feed[0]["friend"]["username"] == "friend"


def test_friend_from_yesterday_evening_does_not_appear(app, friends):
    """
    A friend whose last listen was yesterday evening — less than 24 hours ago
    but on the previous calendar day — should NOT show up as "listening now".

    Regression test for Issue #2: with a rolling 24-hour window, a listen from
    yesterday 11pm still appeared in the feed at 9am the next morning.
    """
    with app.app_context():
        yesterday_evening = (datetime.now(timezone.utc) - timedelta(days=1)).replace(
            hour=23, minute=0, second=0, microsecond=0
        )
        db.session.add(ListeningEvent(
            user_id=friends["friend"].id,
            song_id=friends["song"].id,
            listened_at=yesterday_evening,
        ))
        db.session.commit()

        feed = get_friends_listening_now(friends["viewer"].id)
        assert feed == []  # Bug causes the yesterday-evening listen to appear
