# -*- coding: utf-8 -*-
from contextlib import closing
import pytest
from journal import app
from journal import connect_db
from journal import get_database_connection
from journal import init_db
from flask import session

TEST_DSN = 'dbname=test_learning_journal user=alicija'

def clear_db():
    with closing(connect_db()) as db:
        db.cursor().execute("DROP TABLE entries")
        db.commit()

@pytest.fixture(scope='session')
def test_app():
    """configure our app for use in testing"""
    app.config['DATABASE'] = TEST_DSN
    app.config['TESTING'] = True

@pytest.fixture(scope='session')
def db(test_app, request):
    """initialize the entries table and drop it when finished"""
    init_db()

    def cleanup():
        clear_db()

    request.addfinalizer(cleanup)

@pytest.yield_fixture(scope='function')
def req_context(db):
    """run tests within a test request context so that 'g' is present"""
    with app.test_request_context('/'):
        yield
        con = get_database_connection()
        con.rollback()

def run_independent_query(query, params=[]):
    con = get_database_connection()
    cur = con.cursor()
    cur.execute(query, params)
    return cur.fetchall()

def test_write_entry(req_context):
    from journal import write_entry
    expected = ("My Title", "My Text")
    write_entry(*expected)
    rows = run_independent_query("SELECT * FROM entries")
    assert len(rows) == 1
    for val in expected:
        assert val in rows[0]

def test_get_all_entries_empty(req_context):
    from journal import get_all_entries 
    entries = get_all_entries()
    assert len(entries) == 0

def test_get_all_entries(req_context):
    from journal import get_all_entries, write_entry
    expected = ("My Title", "My Text")
    write_entry(*expected)
    entries = get_all_entries()
    assert len(entries) == 1
    for entry in entries:
        assert expected[0] == entry['title']
        assert expected[1] == entry['text']
        assert 'created' in entry

def test_empty_listing(db):
    actual = app.test_client(). get('/').data
    expected = 'No entries here so far'
    assert expected in actual

@pytest.fixture(scope='function')
def with_entry(db, request):
    from journal import write_entry
    expected = (u'Test Title', u'Test Text')
    with app.test_request_context('/'):
        write_entry(*expected)
        get_database_connection().commit()

    def cleanup():
        with app.test_request_context('/'):
            con = get_database_connection()
            cur = con.cursor()
            cur.execute("DELETE FROM entries")
            con.commit()
    request.addfinalizer(cleanup)

    return expected

def test_listing(with_entry):
    expected = with_entry
    actual = app.test_client().get('/').data
    for value in expected:
        assert value in actual

def test_add_entries(db):
    entry_data = {
        u'title': u'Hello',
        u'text': u'This is a post',
    }
    actual = app.test_client().post(
        '/add', data=entry_data, follow_redirects=True
    ).data
    assert 'No entries here so far' not in actual
    for expected in entry_data.values():
        assert expected in actual

def test_do_login_success(req_context):
    username, password = ('admin', 'admin')
    from journal import do_login
    assert 'logged_in' not in session
    do_login(username, password)
    assert 'logged_in' in session


def test_do_login_bad_password(req_context):
    username = 'admin'
    bad_password = 'wrongpassword'
    from journal import do_login
    with pytest.raises(ValueError):
        do_login(username, bad_password)


def test_do_login_bad_username(req_context):
    password = 'admin'
    bad_username = 'wronguser'
    from journal import do_login
    with pytest.raises(ValueError):
        do_login(bad_username, password)

SUBMIT_BTN = '<input type="submit" value="Share" name="Share"/>'


def login_helper(username, password):
    login_data = {
        'username': username, 'password': password
    }
    client = app.test_client()
    return client.post(
        '/login', data=login_data, follow_redirects=True
    )


def test_start_as_anonymous(db):
    client = app.test_client()
    anon_home = client.get('/').data
    assert SUBMIT_BTN not in anon_home


def test_login_success(db):
    username, password = ('admin', 'admin')
    response = login_helper(username, password)
    assert SUBMIT_BTN in response.data


def test_login_fails(db):
    username, password = ('admin', 'wrong')
    response = login_helper(username, password)
    assert 'Login Failed' in response.data

def test_logout(db):
    home = login_helper('admin', 'admin').data
    assert SUBMIT_BTN in home
    client = app.test_client()
    response = client.get('/logout')
    assert SUBMIT_BTN not in response.data
    assert response.status_code == 302