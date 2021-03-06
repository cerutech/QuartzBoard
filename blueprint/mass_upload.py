import io
import flask
from quartz import auth, image_utils
from datetime import datetime
from server import db
import logging
from werkzeug.utils import secure_filename

mass_upload_api = flask.Blueprint(__name__, 'mass_uploader')

@mass_upload_api.route('/upload/bulk', methods=['GET', 'POST'])
@auth.require(needs=['create_image'])
def mass_upload():
    user_collections = list(db.db.collections.find({'userID': flask.g.user['userID']}))

    if flask.request.method == 'POST':
        data = flask.request.form
        if data['terms'] != 'on':
            return flask.redirect('/profile/upload?terms=1')

        total_done = 0
        images = flask.request.files.getlist('images')
        if len(images) > 20:
            flask.flash('Too many images were uploaded. This action has been reported', 'is-danger')
            return flask.redirect('/upload/bulk')

        new_col = False
        if data.get('new_collection_confirm'):
            new_col = True
            collectionID = db.make_id()
            tags_used = [str(x) for x in data['tags'].split(',') if x is not '']
            new_collection = {'collectionID': collectionID,
                              'userID': flask.g.user['userID'],
                              'title': data['new_collection_title'],
                              'images': [],
                              'created_at': datetime.utcnow(),
                              'uploaded_at': datetime.utcnow(), # for compat purposes
                              'mode': data['new_collection_mode'],
                              'views': [],
                              'likes': [],
                              'tags': []}

            db.db.collections.insert_one(new_collection)

        for image in images:
            #fileID = db.make_token(length=32)
            fileID = db.make_word_token(word_count=4) + '_b' # _b = bulk uploaded

            tags_used = [str(x) for x in data['tags'].split(',')]
            if not tags_used:
                flask.flash('No tags found', 'is-danger')
                return flask.redirect('/upload/bulk')

            new_image = {'userID': flask.g.user['userID'],
                         'filename': secure_filename(image.filename),
                         'uploaded_at': datetime.utcnow(),
                         'tags': tags_used,
                         'fileID': fileID,
                         'views': [],
                         'status': 'public',
                         'rating': data['rating'],
                         'source': data['source'],
                         'processing': True}

            db.db.images.insert_one(new_image)
            author = flask.g.user['userID']
            image_utils.upload_to_quartz(image.stream.read(), fileID, author)
            
            # add to collection if option is selected
            if new_col:
                # new collection is picked
                db.db.collections.update_one({'collectionID': collectionID}, {'$push': {'images': fileID}})
            else:
                if data['collection']:
                    if data['collection'] != 'dont':
                        db.db.collections.update_one({'collectionID': data['collection']}, {'$push': {'images': fileID}})

            total_done += 1

        if data['collection'] and data.get('collection', '') != 'dont':
            return flask.redirect('/collection/{}'.format(data['collection']))
        else:
            return flask.redirect('/profile')

    else:
        return flask.render_template('mass_upload/upload.html', **locals())