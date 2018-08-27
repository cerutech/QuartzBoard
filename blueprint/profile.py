import io
import sys
import flask
import secrets
import threading
import humanize
from quartz import auth
from datetime import datetime
from PIL import Image
from server import db
from gridfs import errors
from werkzeug.utils import secure_filename

profile_api = flask.Blueprint(__name__, 'profile')

def make_thumbnail(image_bytes, size=(128, 128)):
    bio = io.BytesIO()
    img = Image.open(image_bytes)
    img.thumbnail(size, Image.ANTIALIAS)
    img.save(bio, format='PNG')
    bio.seek(0)

    return bio


def process_image(image_bytes, fileID, author=None):
    img = Image.open(image_bytes)

    bio = io.BytesIO()
    # reformat image into a PNG
    try:
        img.save(bio, format='PNG')
        bio.seek(0)
        size = sys.getsizeof(bio)
        print("img size in memory in bytes: ", size)
        if size > (1 * 1024 * 1024): # 1MB
            location = 'S3'
        else:
            location = 'gridFS'

        db.upload_image(bio, fileID, author=author, location=location)
        db.upload_image(make_thumbnail(image_bytes), fileID + '_thumb', author=author, location=location)
        db.db.images.update_one({'fileID': fileID}, {'$set': {'processing': False,
                                                              'location': location}})

    finally:
        # incase of error
        # make sure to dump file from memory
        bio.close()

@profile_api.route('/profile')
@auth.require()
def profile():
    return flask.render_template('profile/dashboard.html')

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

        image = flask.request.files['image']
        #if not image_bytes:
        #    return flask.redirect('/profile/upload')
        tags_used = [str(x) for x in data['tags'].split(',')]

        new_image = {'userID': flask.g.user['userID'],
                     'title': data['title'],
                     'filename': secure_filename(image.filename),
                     'uploaded_at': datetime.utcnow(),
                     'tags': tags_used,
                     'fileID': fileID,
                     'views': [],
                     'status': 'public',
                     'nsfw': True if data.get('is_nsfw', 'off') == "on" else False,
                     'processing': True}

        db.db.images.insert_one(new_image)
        author = flask.g.user['userID']

        process_image(image.stream, fileID, author=author)
        #threading.Thread(None, target=process_image, args=(image.stream, fileID, )).start()
        return flask.redirect('/image/{}'.format(fileID))

    else:

        return flask.render_template('profile/upload.html')

@profile_api.route('/profile/<userID>/avatar')
def get_avatar(userID):
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
    avatar_small = make_thumbnail(new_avatar.stream, size=(256, 256))
    # db exists returns false for all attemtps to check
    db.avatar_storage.delete(flask.g.user['userID'])
    with db.avatar_storage.new_file(_id=str(flask.g.user['userID'])) as fp:
        fp.write(avatar_small.read())

    return flask.redirect('/profile')