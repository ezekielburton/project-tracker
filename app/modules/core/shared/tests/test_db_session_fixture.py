"""The db_session fixture restarts only its own SAVEPOINT, so app code can use
`with db.session.begin_nested():` under tests like it does in production."""
from app.modules.core.shared.models import User


def _user(tag):
    user = User(name=f'Nested {tag}', email=f'nested-{tag}@example.com', role='designer')
    user.set_password('password123')
    return user


def test_with_begin_nested_block_then_more_db_work(db_session):
    with db_session.begin_nested():
        db_session.add(_user('a'))

    db_session.add(_user('b'))
    db_session.flush()
    assert User.query.filter(User.email.like('nested-%@example.com')).count() == 2


def test_with_begin_nested_block_after_a_commit(db_session):
    db_session.add(_user('c'))
    db_session.commit()

    with db_session.begin_nested():
        db_session.add(_user('d'))

    db_session.add(_user('e'))
    db_session.commit()
    assert User.query.filter(User.email.like('nested-%@example.com')).count() == 3
