import flask
import functools
from .database import db

class Auth():
    def require(self, logged_in=True, needs=[], error='Sorry, you do not have permission {need}'):
        """
        Needs = list of permissions that the user must have to 
        access this route
        """
        def wrapper_one(function):
            def wrapper_two(*args, **kwargs):
                # this SHOULD be inside the flask request context
                user = flask.g.user
                if logged_in and not user:
                    return flask.redirect('/login')

                role = user['role']
                image_meta = {}
                if 'fileID' in kwargs:
                    image_meta = db.get_image(kwargs['fileID'])
                    
                if needs:
                    for need in needs:
                        if '|' in need:
                            # OR case in need
                            need_1, need_2 = need.split('|')
                            if (role.has(need_1) or role.has(need_2)):
                                need = '{} / {}'.format(need_1, need_2)

                                return self.perm_error(need, error=error.format(**locals()))

                        if image_meta:
                            if str(image_meta['userID']) != str(user['userID']):
                                if not role.has(need):
                                    # if the current role does not have delete_image
                                    # but the owner is the one listed. let the owner have full permissions
                                    return self.perm_error(need, error=error.format(**locals()))
                        else:
                            if not role.has(need):
                                return self.perm_error(need, error=error.format(**locals()))

                return function(*args, **kwargs)

            wrapper_two.__name__ = function.__name__ # because flask is weirdd

            return wrapper_two
        return wrapper_one

    def perm_error(self, perm_name, error=None):
        return flask.render_template('errors/permission_error.html', **locals())