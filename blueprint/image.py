import io
import flask
import secrets
import requests
import threading
from quartz import auth
from datetime import datetime
from PIL import Image, ImageFont
from server import db
import logging

FONT_LOCATION = 'static/fonts/Lato-Light.ttf'

fonts = [ImageFont.truetype(FONT_LOCATION, x) for x in range(1, 51)]

image_api = flask.Blueprint(__name__, 'image')

def generate_error_image(status_code):
    bytesIO = io.BytesIO()
    im = Image.new((400,400), 'RGBA', '#ff291d')
    font = fonts[25]

    draw = ImageDraw.Draw(im)
    w, h = draw.textsize(status_code)
    draw.text(((W-w)/2,(H-h)/2), status_code, fill="white")
    im.save(bytesIO, format='png')
    bytesIO.seek(0)

    return bytesIO

@image_api.route('/search')
def search():
    to_search = flask.request.args.get('tags','*')
    tags = []
    broken_tags = []

    for tag in to_search.split():
        if tag:
            #if ':' in tag:
            #    spec, val = tag.split(':')
            #    extra_searches[spec] = val

            tag_meta = db.get_tag(tag, search_by='name')
            if tag_meta:
                tags.append(tag_meta.get('tagID'))
            else:
                broken_tags.append(tag)
            if tag_meta:
                db.db.tags.update_one({'tagID': tag_meta['tagID']},
                                      {'$set': {'searches': tag_meta['searches'] + 1}})

    results = db.get_images(tags=tags,
                            page_number=flask.request.args.get('page', '1'))

    total_pages = db.get_page_count(len(results))

    return flask.render_template('image/search.html', **locals())

@image_api.route('/image/<fileID>')
def show_image(fileID):
    
    image_meta = db.db.images.find_one({'fileID': fileID})
    if not image_meta:
        return flask.render_template('errors/404.html', error='The requested image does not exist')

    image_views = db.set_image_views(fileID, flask.request.remote_addr)

    return flask.render_template('image/show.html', **locals())

@image_api.route('/api/image/<fileID>/delete')
@auth.require(needs=['delete_image'])
def delete_image(fileID):
    if not flask.g.is_logged_in:
        return flask.jsonify({'success': False,
                              'msg': 'You are not logged in'})



    image_meta = db.db.images.find_one({'fileID': fileID})
    if not image_meta['userID'] == flask.g.user['userID']:
        # uh oh??
        return flask.jsonify({'success': False,
                              'msg': 'You do not own this image'})

    db.delete_image(fileID)
    db.db.images.remove({'fileID': fileID})
    return flask.jsonify({'success': True,
                          'msg':'Deleted image'})


@image_api.route('/api/image/<fileID>')
def get_image(fileID):
    image_meta = db.db.images.find_one({'fileID': fileID})
    if not image_meta:
        return flask.redirect('/static/image/404.jpg')

    if image_meta.get('location', 'gridFS') == 'gridFS':
        try:
            file = db.get_image(fileID)
        except AttributeError:
            # file is missing
            # mark as private and continue
            db.db.images.update_one({'fileID': fileID}, {'$set': {'status': 'private'}})

    else:
        url = db.base_url + str(image_meta['userID']) + '/' + fileID + '.png'
        resp = requests.head(url)
        logging.error(resp.status_code)
        if resp.status_code == 200:
            return flask.redirect(url)
        else:
            # file is missing from S3 storage
            # mark as private
            db.db.images.update_one({'fileID': fileID}, {'$set': {'status': 'private'}})


    return flask.send_file(io.BytesIO(file),
                           mimetype='image/png')

@image_api.route('/api/image/<fileID>/thumbnail')
def show_image_thumbnail(fileID):
    image_meta = db.db.images.find_one({'fileID': fileID})

    if image_meta.get('location', 'gridFS') == 'gridFS':

        try:
            file = db.get_image(fileID + '_thumb')
        except AttributeError:
            # file is missing
            db.db.images.remove({'fileID': fileID})
            file = generate_error_image(404)
    else:
        return flask.redirect(db.base_url + str(image_meta['userID']) + '/' + fileID + '_thumb' + '.png')

    return flask.send_file(io.BytesIO(file),
                           mimetype='image/png')


@image_api.route('/api/tags/check', methods=['POST'])
def get_tag():
    data = flask.request.form
    print(data)
    # check a tags name
    tag_meta = db.get_tag(data['tag_name'], search_by='name')
    if not tag_meta:
        return flask.jsonify({'success': True,
                              'needs_adding': True})

    else:
        del tag_meta['_id']
        return flask.jsonify({'success': True,
                              'tag': tag_meta})


@image_api.route('/api/tags/create', methods=['POST'])
def create_tag():
    data = flask.request.form
    tag_meta = db.db.tags.find_one({'name': data['tag_name']})

    if tag_meta:
        del tag_meta['_id']
        return flask.jsonify(tag_meta)

    if not data['tag_name']:
        return flask.jsonify({'success':False, 'msg': 'Tag name is missing'})

    if not data['type']:
        return flask.jsonify({'success':False, 'msg': 'Tag type is missing'})

    tag_data = {'name': data['tag_name'],
                'type': data['type'],
                'tagID': db.make_id(length=18),
                'uses': 1,
                'searches':0,
                'created_by': flask.g.user['userID'],
                'created_at': datetime.utcnow().timestamp(),
                'likes':[]}

    if data['type'] == 'character' and data.get('fandom'):
        tag_data['fandom'] = data['fandom']

    db.db.tags.insert_one(tag_data)
    del tag_data['_id']
    return flask.jsonify({'success': True,
                          'tag': tag_data})

@image_api.route('/api/tags/<tagID>/like')
def like_tag(tagID):
    db.like_tag(tagID, flask.g.user['userID'])

    return flask.jsonify({'success': True})

@image_api.route('/api/tags/<tagID>/unlike')
def dislike_tag(tagID):
    db.unlike_tag(tagID, flask.g.user['userID'])

    return flask.jsonify({'success': True})

@image_api.route('/api/tags/render_tag_list', methods=['POST'])
def render_tag_list():
    tags = flask.request.get_json()
    tags = [x for x in tags if x is not None]
    return flask.jsonify({'success': True,
                          'html': flask.render_template('image/utils/render_tag_list.html', **locals())})

@image_api.route('/api/image/generate_avatar')
def gen_ava():
    return flask.send_file(db.generate_avatar(hash=flask.request.remote_addr), mimetype='image/png')