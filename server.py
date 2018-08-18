import os; os.chdir(os.path.realpath(__file__).replace('server.py',''))
import flask
import humanize
import logging
import  flask_profiler
from quartz import *

logger = logging.getLogger('quartz.main')

app = flask.Flask(__name__)
app.config['TEMPLATES_AUTO_RELOAD'] = True
app.config['SECRET_KEY'] = db.config.secret_key
app.config['MAX_CONTENT_LENGTH'] = 8 * 1024 * 1024

app.config["flask_profiler"] = {
    "enabled": db.config.developer_mode,
    "storage": {
        "engine": "mongodb"
    },
    "basicAuth":{
        "enabled": True,
        "username": "admin",
        "password": "superSecurePassword"
    },
    'endpointRoot':'admin_profiler',
    "ignore": [
	    "^/static/.*"
	]
}

@app.route('/')
def index():
    images = db.get_images(page_number=1, page_size=5)
    return flask.render_template('home.html', **locals())

@app.route('/about')
def about():
    return flask.render_template('about.html')

@app.route('/ui_mode')
def switch_mode():
    mode = flask.request.args.get('mode','light')
    print(mode)
    resp = flask.make_response(flask.redirect('/'))
    if mode == 'dark':
        resp.set_cookie('dark_mode', 'on')
    else:
        resp.set_cookie('dark_mode', 'off')
    return resp

@app.route('/confirm', methods = ['GET', 'POST'])
def confirm_age():
    if flask.request.method == 'POST':
        resp = flask.make_response(flask.redirect('/?confirmed=1'))
        resp.set_cookie('confirmed', '1')
        return resp
    else:
        return flask.render_template('confirm.html')

@app.before_request
def utility_processor():
    user = {}
    is_logged_in = False
    flask.g.is_logged_in = False

    token = flask.request.cookies.get('token')
    if token:
        user = db.get_user(token, search_by='token')
        if not user:
            # user token is invalid
            flask.g.user = {}
            flask.g.is_logged_in = False
            
        else: 
            flask.g.user = user 
            flask.g.is_logged_in = True
            is_logged_in = True
    else:
        flask.g.user = {}
        
    try:
        rule = flask.request.url_rule.rule
    except:
        # 404?
        return flask.render_template('errors/404.html',error= '404'), 404

    if 'static' not in rule or 'api' not in rule:
        if not flask.request.cookies.get('confirmed') and ('confirm' not in flask.request.url_rule.rule):
            return flask.redirect('/confirm')


@app.context_processor
def ctx_processor():
    return {'user': flask.g.user,
            'is_logged_in': flask.g.is_logged_in,
            'dark_mode': flask.request.cookies.get('dark_mode', 'off'),
            'enable_nsfw': flask.request.cookies.get('enable_nsfw', '0')}

if __name__ == '__main__':
    from blueprint.auth import auth_api
    from blueprint.profile import profile_api
    from blueprint.image import image_api

    app.register_blueprint(auth_api)
    app.register_blueprint(profile_api)
    app.register_blueprint(image_api)
    
    template_functions = {'get_popular_tags': db.get_popular_tags,
                          'get_user': db.get_user,
                          'get_tag': db.get_tag,
                          'time_to_human': humanize.naturaltime,
                          'get_images': db.get_images,
                          'db': db}

    app.jinja_env.globals.update(**template_functions)

    flask_profiler.init_app(app)

    app.run('0.0.0.0', db.config.get('port', 8081), threaded=True)
