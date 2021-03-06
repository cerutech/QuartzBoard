import io
import flask
import secrets
import requests
import threading
from quartz import auth, image_utils
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

@image_api.route('/old_search')
def old_search():
    current_page = int(flask.request.args.get('page', 1))
    if current_page == 0:
        current_page = 1
    

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
                            page_number=current_page)

    return flask.render_template('image/search.html', **locals())

@image_api.route('/search')
def search():
    current_page = int(flask.request.args.get('page', 1))
    if current_page == 0:
        current_page = 1

    search_tags = flask.request.args.get('tags', 'any').split()
    rating = 'any'
    userID = 'any'
    fandom = 'any'
    for tag in search_tags:
        if 'rating:' in tag:
            rating = tag.split(':')[1]
        if 'user:' in tag:
            user = tag.split(':')[1]


    results = db.search_items(tag_names=search_tags,
                               rating=rating,
                               user=userID,
                               page_number=current_page,
                               count=True,
                               return_dict=True,
                               page_size=40)

    if 'is_collection' in search_tags:
        is_collection = True

    return flask.render_template('image/search.html', **locals())

@image_api.route('/image/<fileID>')
def show_image(fileID):
    
    image_meta = db.db.images.find_one({'fileID': fileID})
    if not image_meta:
        return flask.render_template('errors/404.html', error='The requested image does not exist')

    image_views = db.set_image_views(fileID, flask.request.remote_addr)
    collection = db.db.collections.find_one({'images': {'$all': [fileID]}})

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

@image_api.route('/api/image/check')
def check_existing():
    data = flask.request.get_json()
    print(data)


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
            file = db.get_image(fileID + '_thumbnail')
        except AttributeError:
            # file is missing
            db.db.images.remove({'fileID': fileID})
            file = generate_error_image(404)
    else:
        return flask.redirect(db.base_url + str(image_meta['userID']) + '/' + fileID + '_thumbnail' + '.png')

    return flask.send_file(io.BytesIO(file),
                           mimetype='image/png')

@image_api.route('/api/tags/find', methods=['GET'])
def find_tags_by_name():
    tag_name = flask.request.args.get('name')
    tags = []
    found_tags = list(db.db.tags.find({'internal_name': {'$regex':'^{}'.format(db.make_internal_name(tag_name))}}))
    for t in found_tags:
        del t['_id']
        tags.append(t)

    return flask.jsonify(tags[:10])


@image_api.route('/api/tags/check', methods=['POST'])
def get_tag():
    """
    As of 0.7:
    Decprecated. Only for use with Bulk uploading for the time being
    """
    data = flask.request.form
    # check a tags name
    tag_meta = list(db.db.tags.find({'internal_name': db.make_internal_name(data['tag_name'])})) #get_tag(data['tag_name'], search_by='name')

    if len(tag_meta) == 1:
        tag_meta = tag_meta[0]
        del tag_meta['_id']
        return flask.jsonify({'success': True,
                              'tag': tag_meta})
    else:
        tags = tag_meta
        return flask.jsonify({'success': True,
                              'multiple_choice': True,
                              'html': flask.render_template('image/utils/multi.html', **locals())})

    # DECPRECEATED for now
    #if not tag_meta:
    #    return flask.jsonify({'success': True,
    #                          'needs_adding': True})

@image_api.route('/api/tags/create', methods=['POST'])
def create_tag():
    data = flask.request.form
    print(data)
    tag_meta = db.db.tags.find_one({'internal_name': db.make_internal_name(data['tag_name'])})

    if not data.get('tag_name'):
        return flask.jsonify({'success':False, 'msg': 'Tag name is missing'})

    if not data.get('type'):
        return flask.jsonify({'success':False, 'msg': 'Tag type is missing'})

    if tag_meta:
        bypass = False
        print(tag_meta['type'])
        print(data['type'])
        if tag_meta['name'] == data['tag_name'] and tag_meta['type'] == data['type']:
            # check if type is character and fandom is not the same
            if tag_meta['type'] == 'character':
                if tag_meta.get('fandom_internal') and db.make_internal_name(data.get('fandom', ' ')):
                    if tag_meta.get('fandom') != data.get('fandom'):
                        bypass = True
                    else:
                        # if the tag is not type:character and fandom is not the same
                        return flask.jsonify({'success': False, 'msg': 'Tag already exists'})

            if not bypass:
                return flask.jsonify({'success': False, 'msg': 'Tag already exists'})

    if data['type'] != 'custom':
        tag_data = {'name': data['tag_name'],
                    'internal_name': db.make_internal_name(data['tag_name']),
                    'type': data['type'],
                    'tagID': db.make_id(length=18),
                    'uses': 1,
                    'searches':0,
                    'created_by': flask.g.user['userID'],
                    'created_at': datetime.utcnow().timestamp(),
                    'likes':[]}
    else:
        tag_data = {'name': data['tag_name'],
                    'internal_name': db.make_internal_name(data['tag_name']),
                    'type': data['tag_type'],
                    'tagID': db.make_id(length=18),
                    'uses': 1,
                    'searches':0,
                    'created_by': flask.g.user['userID'],
                    'created_at': datetime.utcnow().timestamp(),
                    'likes':[],
                    'colour': data.get('tag_colour', 'blue')}

    if data['type'] == 'character' and data.get('fandom'):
        tag_data['fandom'] = data['fandom']
        tag_data['fandom_internal'] = db.make_internal_name(data['fandom'])

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
    _tmp = []
    for i, tag in enumerate(tags):
        try:
            int(tag) # check if the tag is of type ID
        except:
            _tmp.append(tag)
        else:
            tag = db.get_tag(str(tag))
            _tmp.append(tag)

    tags = _tmp
        
    return flask.jsonify({'success': True,
                          'html': flask.render_template('image/utils/render_tag_list.html', **locals())})

@image_api.route('/api/image/generate_avatar')
def gen_ava():
    return flask.send_file(db.generate_avatar(hash=flask.request.remote_addr), mimetype='image/png')

@image_api.route('/image/<fileID>/edit', methods=['GET', 'POST'])
@auth.require(needs=['edit_image'])
def edit_image(fileID):
    image_meta = db.db.images.find_one({'fileID': fileID})
    if flask.request.method == 'POST':
        to_set = {}
        data = flask.request.form
        to_set['rating'] = data['rating']
        to_set['source'] = data['source']
        tags = set([x for x in data['tags'].split(',') if x])
        to_set['tags'] = list(tags)
        db.db.images.update_one({'fileID': fileID}, {'$set': to_set})
        flask.flash('Updated image!', 'is-success')
        return flask.redirect('/image/' + fileID + '/edit')
    
    return flask.render_template('image/editor.html', **locals())

@image_api.route('/api/image/<fileID>/tags')
@auth.require(needs=['edit_image'])
def get_image_tags(fileID):
    image_meta = db.db.images.find_one({'fileID': fileID})
    tags = []
    for t in image_meta['tags']:
        t = db.get_tag(t)
        del t['_id']
        tags.append(t)

    return flask.jsonify(tags)

@image_api.route('/api/sourcenao', methods=['GET', 'POST'])
def find_source():
    if flask.request.method == 'POST':
        file = flask.request.files['file']
        data = requests.post('https://saucenao.com/search.php?output_type=2&api_key={}'.format(db.config.get('source_nao_key', '')), data={}, files={'file': file})
        return flask.jsonify(data.json()['results'])

    else:
        data = requests.get('https://saucenao.com/search.php?output_type=2&api_key={}&url={}'.format(db.config.get('source_nao_key', ''), flask.request.args['url']))
        return flask.jsonify(data.json()['results'])