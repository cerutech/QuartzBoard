import io
import sys
import flask
import secrets
import threading
import humanize
import tempfile
from quartz import auth, image_utils
from datetime import datetime
from PIL import Image
from server import db
from gridfs import errors
from werkzeug.utils import secure_filename

profile_api = flask.Blueprint(__name__, 'profile')

@profile_api.route('/profile')
@auth.require()
def profile():
    collections = list(db.db.collections.find({'userID': flask.g.user['userID']}))

    return flask.render_template('profile/dashboard.html', **locals())

@profile_api.route('/profile/upload', methods=['GET','POST'])
@auth.require(needs=['create_image']) # require the create_image permission
def upload_image():
    if not flask.g.is_logged_in:
        return flask.redirect('/login')

    if flask.request.method == 'POST':
        data = flask.request.form
        if data['terms'] != 'on':
            return flask.redirect('/profile/upload?terms=1')

        #fileID = db.make_token(length=32)
        fileID = db.make_word_token(word_count=4)
        print([(k, v) for k,v in data.items()])
        image = flask.request.files['image']
        #if not image_bytes:
        #    return flask.redirect('/profile/upload')
        tags_used = [str(x) for x in data['tags'].split(',')]
        print(tags_used)

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


        #process_image(image.stream, fileID, author=author)
        #threading.Thread(None, target=process_image, args=(image.stream, fileID, )).start()
        return flask.redirect('/image/{}'.format(fileID))

    else:

        return flask.render_template('profile/upload.html')

@profile_api.route('/api/profile/update', methods=['POST'])
@auth.require()
def update_profile():
    data = flask.request.form
    to_set = {}

    if data.get('sidebar_content') != flask.g.user.get('sidebar', {}).get('content'):
        to_set['sidebar.content'] = data['sidebar_content']

    if data.get('patreon') != flask.g.user.get('links', {}).get('patreon') and 0: # depreciated
        pass
        #if '://www.patreon.com/' in data['patreon']:
        #    to_set['links.patreon'] = data['patreon']

    if to_set:
        db.db.users.update_one({'userID': flask.g.user['userID']}, {'$set': to_set})

        return flask.jsonify({'success': True})
    else:
        return flask.jsonify({'success': False, 'msg': 'No changes were made'})

@profile_api.route('/profile/<userID>/avatar')
def get_avatar(userID):
    """
    I wrote the entire avatar system while drunk.
    There may be some operational problems such as the URL's
    not matching the standard
    """
    user_meta = db.db.users.find_one({'userID': userID})
    if not user_meta:
        return flask.redirect('/static/image/404.jpg')

    file = db.avatar_storage.find_one(userID)
    if not file:
        avatar = db.generate_avatar()

        with db.avatar_storage.new_file(_id=userID) as fp:
            fp.write(avatar)

        file = db.avatar_storage.find_one(userID)
        
    file = file.read()

    return flask.send_file(io.BytesIO(file),
                        mimetype='image/png')


@profile_api.route('/profile/avatar/upload', methods=['POST'])
@auth.require(needs=['upload_avatar'])
def upload_new_avatar():
    new_avatar = flask.request.files['avatar']
    avatar_small = image_utils.thumbnail(new_avatar.stream, width=256)
    # db exists returns false for all attemtps to check
    db.avatar_storage.delete(str(flask.g.user['userID']))
    with db.avatar_storage.new_file(_id=str(flask.g.user['userID'])) as fp:
        fp.write(avatar_small.read())

    return flask.redirect('/profile')