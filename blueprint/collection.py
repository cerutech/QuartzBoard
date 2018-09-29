import io
import flask
import secrets
import requests
from quartz import auth, image_utils
from datetime import datetime
from server import db
import logging

collection_api = flask.Blueprint(__name__, 'collection')

# show_collection.html
@collection_api.route('/collection/<collectionID>', methods=['GET'])
def show_collection(collectionID):
    collection = db.db.collections.find_one({'collectionID': collectionID})
    page = int(flask.request.args.get('page', 0))
    if flask.request.args.get('goto_page', ''):
        for i, image in enumerate(collection['images']):
            if str(flask.request.args.get('goto_page', '')) == image:
                page = i + 1

    if page == 0:
        # show collection index!!
        return flask.render_template('collection/collection_index.html', **locals())



    image_meta = collection['images'][page - 1]
    image_meta = db.db.images.find_one({'fileID': image_meta})
    if image_meta is None:
        return flask.render_template('collection/image_missing.html', **locals())

    return flask.render_template('collection/show_collection.html', **locals())


@collection_api.route('/api/collection/create', methods=['GET', 'POST'])
@auth.require(needs=['create_collection'])
def create_new_collection():
    if flask.request.method == 'POST':
        data = flask.request.form
        if db.db.collections.find_one({'userID': flask.g.user['userID'],
                                    'title': data['title']}):
            flask.flash('You already have a collection with that name', 'is-error')
            return flask.redirect('/profile')

        id = db.make_id()
        new_collection = {'collectionID': id,
                          'userID': flask.g.user['userID'],
                          'title': data['title'],
                          'images': [],
                          'created_at': datetime.utcnow(),
                          'languages': [{'lang': data['language'], 'collectionID': id}],
                          'views': [],
                          'likes': []}

        db.db.collections.insert_one(new_collection)
        return flask.redirect('/collection/{}/edit'.format(id))

    else:
        return flask.render_template('collection/create.html')

@collection_api.route('/collection/<collectionID>/edit', methods=['GET', 'POST'])
@auth.require(needs=['edit_collection'])
def edit_collcetion(collectionID):
    collection = db.db.collections.find_one({'collectionID': collectionID})
    if not collection:
        flask.flash('This collection does not exist', 'is-error')
        return flask.redirect('/profile#dash_collections')

    user_images = list(db.db.images.find({'userID': flask.g.user['userID']}))
    
    return flask.render_template('collection/edit.html', **locals())
  
@collection_api.route('/api/collection/<collectionID>/delete', methods=['GET', 'POST'])
@auth.require(needs=['delete_collection'])
def api_delete_collcetion(collectionID):
    collection = db.db.collections.find_one({'collectionID': collectionID})
    if not collection:
        flask.flash('This collection does not exist', 'is-error')
        return flask.redirect('/dashboard#dash_collections')

    db.db.collections.remove_one({'collectionID': collectionID})
    return flask.redirect('/profile')


@collection_api.route('/api/collection/<collectionID>/edit', methods=['GET', 'POST'])
@auth.require(needs=['edit_collection'])
def api_edit_collcetion(collectionID):
    collection = db.db.collections.find_one({'collectionID': collectionID})
    if not collection:
        flask.flash('This collection does not exist', 'is-error')
        return flask.redirect('/dashboard#dash_collections')

    if flask.request.method == 'POST':
        to_edit = flask.request.form
        images = to_edit['images'].split(',')
        confirmed_images = []
        for img in images:
            image_meta = db.db.images.find_one({'fileID': img})
            if not image_meta:
                flask.flash('Image {} not found'.format(img), 'is-danger')
                return flask.redirect('/collection/{}/edit'.format(collectionID))

            if image_meta['userID'] != flask.g.user['userID']:
                flask.flash('Image {}. You do not own this image'.format(img), 'is-danger')
                return flask.redirect('/collection/{}/edit'.format(collectionID))
                
            confirmed_images.append(image_meta['fileID'])

        db.db.collections.update_one({'collectionID': collectionID}, {'$set': {'images': confirmed_images,
                                                                               'title': to_edit['title']}})
        flask.flash('Updated this collection!', 'is-success')

    return flask.redirect('/collection/{}/edit'.format(collectionID))