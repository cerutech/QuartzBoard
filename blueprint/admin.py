import flask
from datetime import datetime
from server import db
from quartz import auth, utils
import logging

admin_api = flask.Blueprint(__name__, 'admin')

# ROLE SYSTEM
@admin_api.route('/admin/roles')
@auth.require(needs=['edit_roles'])
def roles():
    roles = list( db.db.roles.find())
    return flask.render_template('admin/roles.html', **locals())


@admin_api.route('/api/admin/roles/create', methods=['POST'])
@auth.require(needs=['edit_roles'])
def new_role():
    data = flask.request.form
    role_meta = db.db.roles.find_one({'name': data['name']})
    if role_meta:
        flask.flash('Role name already exists', 'is-warning')
        return flask.redirect('/admin/roles')
    new_role = {'name': data['name'],
                'roleID': db.make_id(),
                'permissions': db.role_defaults}

    db.db.roles.insert_one(new_role)
    return flask.redirect('/admin/roles/' + new_role['roleID'])

@admin_api.route('/admin/roles/give')
@auth.require(needs=['edit_roles'])
def give_roles():
    return flask.render_template('admin/role_give.html', **locals())

@admin_api.route('/admin/roles/<roleID>')
@auth.require(needs=['edit_roles'])
def edit_role(roleID):
    role = db.db.roles.find_one({'roleID': roleID})
    permissions = db.wrap_permissions(**role['permissions'])
    roles = list(db.db.roles.find())
    return flask.render_template('admin/role_edit.html', **locals())

@admin_api.route('/api/admin/roles/<roleID>/edit', methods=['POST'])
@auth.require(needs=['edit_roles'])
def edit_role_api(roleID):
    data = flask.request.form
    role_meta = db.db.roles.find_one({'roleID': roleID})
    to_set = {}

    for k, v in role_meta['permissions'].items():
        # checkboxes do not send data if they are not checked
        
        if k in data:
            to_set['permissions.{}'.format(k)] =  utils.checkbox_to_bool(data[k])
        else:
            to_set['permissions.{}'.format(k)] =  False

    db.db.roles.update_one({'roleID': roleID}, {'$set': to_set})

    return flask.redirect('/admin/roles/' + role_meta['roleID'])

@admin_api.route('/api/admin/roles/<roleID>/give/<userID>', methods=['POST'])
@auth.require(needs=['edit_roles'])
def give_role_to_user(roleID, userID):
    if roleID != 'remove':
        role_meta = db.db.roles.find_one({'roleID': roleID})
    else:
        role_meta = {'roleID': ''}

    db.db.users.update_one({'userID': userID}, {'$set': {'roleID': role_meta['roleID']}})
    return flask.jsonify({'success': True})

@admin_api.route('/api/admin/roles/user_list', methods=['POST'])
@auth.require(needs=['edit_roles'])
def show_user_list():
    users = list(db.db.users.find({"username": flask.request.args['q']}))
    roles = list(db.db.roles.find())
    return flask.jsonify({'success':True, 'html': flask.render_template('admin/utils/user_list.html', **locals())})