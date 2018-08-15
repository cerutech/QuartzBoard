import flask

import secrets
from passlib.hash import argon2
from server import db
from datetime import datetime

auth_api = flask.Blueprint(__name__, 'auth')

def hash_password(password):
    return argon2.hash(password)

def verify_password(password, database_password):
    return argon2.verify(password, database_password)

@auth_api.route('/create', methods=['GET','POST'])
def create_user():
    if flask.request.method == 'POST':
        # ok, here we go
        data = flask.request.form

        new_user = {'username': data['username'],
                    'password_hash': hash_password(data['password']),
                    'token': db.make_token(length=64),
                    'userID': db.make_id(length=18),
                    'created_at': datetime.utcnow()}

        db.db.users.insert_one(new_user)
        resp = flask.make_response(flask.redirect('/?new_user=1'))
        resp.set_cookie('token', value=new_user['token'])
        return resp


    else:
        return flask.render_template('auth/create.html')

@auth_api.route('/login', methods=['GET','POST'])
def login_user():
    if flask.request.method == 'POST':
        data = flask.request.form
        user = db.get_user(data['username'], search_by='username', safe_mode=False)
        if not user:
            flask.flash('Username/password is not correct', 'error')
            return flask.redirect('/login')

        if verify_password(data['password'], user['password_hash']):
            resp = flask.make_response(flask.redirect('/?logged_in=1'))
            resp.set_cookie('token', value=user['token'])
            return resp

        else:
            flask.flash('Username/password is not correct', 'error')
            return flask.redirect('/login')

        if not user:
            flask.flash('Username/password is not correct', 'error')
            return flask.redirect('/login')

    else:
        return flask.render_template('auth/login.html')

@auth_api.route('/logout')
def logout():
    resp = flask.make_response(flask.redirect('/'))
    resp.set_cookie('token', '')
    return resp