import io
import sys
import flask
import secrets
import threading
import humanize
from datetime import datetime
from PIL import Image
from server import db
from werkzeug.utils import secure_filename

profile_api = flask.Blueprint(__name__, 'profile')

def process_image(image_bytes, fileID, author=None):
    img = Image.open(image_bytes)

    bio = io.BytesIO()
    # reformat image into a PNG
    try:
        img.save(bio, format='PNG')
        bio.seek(0)

        thumb = img.copy()
        thumb.thumbnail((128, 128), Image.ANTIALIAS)

        bio_thumb = io.BytesIO()
        thumb.save(bio_thumb, format='PNG')
        bio_thumb.seek(0)
        
        print("img size in memory in bytes: ", humanize.naturalsize(sys.getsizeof(bio)))

        db.upload_image(bio, fileID, author=author)
        db.upload_image(bio_thumb, fileID + '_thumb', author=author)
        db.db.images.update_one({'fileID': fileID}, {'$set': {'processing': False}})

    finally:
        # incase of error
        # make sure to dump file from memory
        bio.close()
        bio_thumb.close()


@profile_api.route('/profile')
def profile():
    # shows your profile
    if not flask.g.is_logged_in:
        return flask.redirect('/login')

    return flask.render_template('profile/dashboard.html')


@profile_api.route('/profile/upload', methods=['GET','POST'])
def upload_image():
    if not flask.g.is_logged_in:
        return flask.redirect('/login')

    if flask.request.method == 'POST':
        data = flask.request.form

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
                     'processing': True}

        db.db.images.insert_one(new_image)
        author = None
        if not db.config.use_gridfs:
            author = flask.g.user['userID']

        process_image(image.stream, fileID, author=author)
        #threading.Thread(None, target=process_image, args=(image.stream, fileID, )).start()
        return flask.redirect('/image/{}'.format(fileID))

    else:

        return flask.render_template('profile/upload.html')
