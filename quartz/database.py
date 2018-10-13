import io
import secrets
import pymongo
import gridfs
import hashlib
import boto3
import json
import logging
import pagan # avatar generator

logger = logging.getLogger('quartz')
logger.setLevel(logging.DEBUG)
# create file handler which logs even debug messages
fh = logging.FileHandler('QuantumQuartz.log')
fh.setLevel(logging.DEBUG)
# create console handler with a higher log level
ch = logging.StreamHandler()
ch.setLevel(logging.INFO)
# create formatter and add it to the handlers
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
ch.setFormatter(formatter)
# add the handlers to the logger
logger.addHandler(fh)
logger.addHandler(ch)

class Permissions():
    def __init__(self, name='', **kwargs):
        """
        Some explaining: 
        All permissions start with a prefix. This is either:
        create_, edit_, delete_
        These are sub-permissions of the general:
        craete, edit, delete

        IF YOU GIVE A ROLE ANY OF THE ABOVE PERMISSIONS THEN
        THE ROLE WILL HAVE FULL PERMISSIONS TO DO ANY OF THOSE ACTIONS
        For instance, if a role has edit=True then they have full permissions to edit 
        tags, images etc..
        """
        self.name = name
        defaults = json.load(open('config/role_defaults.json'))

        for k, v in kwargs.items():
            defaults[k] = v

        self.permissions = defaults
        

    def has(self, perm_name):
        if not perm_name in self.permissions:
            raise TypeError('Permission "{}" does not exist'.format(perm_name))

        prefix = perm_name.split('_')[0]

        if self.permissions.get(prefix, False):
            return True # return true if the role has edit, create or delete set

        return self.permissions[perm_name]

ROLES = {'admin': Permissions(edit=True,
                              create=True,
                              delete=True,
                              name='Admin'),
         'user': Permissions(name='User')}


site_config = json.load(open('config/site.json'))

try:
    config = json.load(open('config.json'))
except FileNotFoundError:
    config = {}
except json.JSONDecodeError:
    logging.error('JSON config is malformed. Using default config')
    config = {}

config['site'] = site_config

class RecordObject():
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._set(**kwargs)

    def get(self, key, default=None):
        if hasattr(self, key):
            return getattr(self, key, default)
        else:
            return default
        
    def _set(self, **kwargs):
        for k,v in kwargs.items():
            try:
                v['']
            except KeyError:
                v = RecordObject(**v)
            except:
                pass

            setattr(self, k, v)

    def set(self, **kwargs):
        return self._set(**kwargs)

    def __str__(self):
        s = '<RecordObject '
        items = []
        for item in dir(self):
            if item.startswith('__'):
                continue

            if not callable(item):
                items.append(str(item))

        return s + ', '.join(items) + '>'

class Utils():
    def b64_encode(self, data):
        return secrets.base64.b64encode(data).decode("ascii")

class DataBase:
    def __init__(self):
        self.__version__ = '0.6c (Ruby)'
        self.config = RecordObject(**config)
        
        self.db_connection = pymongo.MongoClient(self.config.mongoURI)

        self.db = self.db_connection.quartz

        self.grid_storage = gridfs.GridFS(self.db_connection.image_storage)
        self.avatar_storage = gridfs.GridFS(self.db_connection.avatar_storage)

        session = boto3.session.Session()
        
        self.logger = logging.getLogger('quartz.database')

        if not self.config.get('developer_mode'):
            self.logger.debug('Not using Developer Mode. Debug endpoints are closed.')
            self.config.set(developer_mode=False)

        # get user roles from database
        roles = self.db.roles.find()

        self.roles = {}
        if not roles:
            # if there are no user created roles
            # then set the current roles as that of the defaults
            self.roles = ROLES
        else:
            for role in roles:
                self.roles[role['name']] = Permissions(**role['permissions'])

        self.role_defaults = json.load(open('config/role_defaults.json'))

        # use DigitalOcean's Spaces API to handle
        # file storage

        # is interchangable with S3

        self.base_url = 'https://{}.nyc3.cdn.digitaloceanspaces.com/'.format(self.config.spaces.bucket_name)

        self.spaces = session.client('s3',
                                     region_name='nyc3',
                                     endpoint_url='https://nyc3.digitaloceanspaces.com',
                                     aws_access_key_id=self.config.spaces.access_key,
                                     aws_secret_access_key=self.config.spaces.access_private)

        self.utils = Utils()
        
        self.flags = {} # this is different to config as flags are set dynamicly
        # these are a set of items where functionality of the server can be toggled
        # if a function of hte server requires a optional config, then the flag can be set if the config is there and ready

        if not self.config.get('spaces'):
            self.flags['no_s3'] = True
        else:
            self.flags['no_s3'] = False

    def get_user(self, userID, search_by='userID', safe_mode=True):
        user = self.db.users.find_one({search_by: userID})
        if not user:
            return {}
         
        if safe_mode:
            del user['token']
            del user['password_hash']

        return user

    def generate_avatar(self, hash=None):
        """
        Generate a avatar from a random hash
        
        Returns a bytesIO object
        """
        if not hash:
            hash = secrets.token_urlsafe(16)

        avatar = pagan.Avatar(hash, pagan.SHA512)
        bio = io.BytesIO()
        avatar.img.save(bio, format='PNG')
        bio.seek(0)
        return bio

    def upload_image(self, image_bytes, fileID, author=None, location='gridFS'):
        if location == 'gridFS':
            with self.grid_storage.new_file(_id=fileID) as fp:
                fp.write(image_bytes)

        else:
            image_bytes.seek(0)
            self.spaces.put_object(ACL='public-read',
                                   Bucket=self.config.spaces.bucket_name,
                                   Body=image_bytes,
                                   Key=str(author) + '/' + fileID + '.png',
                                   ContentType='image/png')

        logger.info('Saving image {} to {}'.format(fileID, location))

    def get_image(self, fileID):
        """
        Get raw bytes from the gridFS storage system
        Does not work if the location on image_meta is set
        to S3
        """
        return self.grid_storage.find_one({'_id': fileID}).read()

    def db_resp(self, resp):
        """
        Helper function to wrap database responses
        """
        return list(resp)

    def get_images(self, tags=[], author=None, page_number=1, page_size=20, sort_by='uploaded_at'):
        """
        Main function for most things in Quartz.
        Tags is a list of tagID's that are stored in the tags collection
        Author is if you want to search by an uploader.
        page_number is the current page number for spliting the results into page_size segments
        page_size is how many images you want to display per page
        sort_by is the field in the database you want to sort by - Defaults to uploaded_at
        """
        skips = page_size * (int(page_number ) - 1)
        if author:
            return self.db_resp(self.db.images.find({'userID': str(author)}).sort(sort_by, -1).skip(skips).limit(page_size))

        if not tags:
            return self.db_resp(self.db.images.find().sort(sort_by, -1).skip(skips).limit(page_size))
        else:
            tags = [str(x) for x in tags if x]

            query = self.db.images.find({'tags': {'$all': tags}}).sort(sort_by, -1).skip(skips).limit(page_size)

        return list(query)

    def search_images(self, tag_names=[], rating='any', author='any', sort_by='uploaded_at', page_number=1, page_size=20, count=False):
        skips = page_size * (int(page_number ) - 1)
        tags = []
        for tag in tag_names:
            if ':' not in tag:
                tag_meta = self.db.tags.find({'internal_name': tag.lower()})
            else:
                type, name = tag.lower().split(':')
                search_query = {'internal_name': name.lower(), 'type': type}
                print(name)
                if '(' in name and ')' in name and type == 'character':
                    # we have a fandom to search by
                    search_query['fandom_internal'] = name.split('(')[1].split(')')[0].lower()
                    search_query['internal_name'] = name.split('(')[0]

                tag_meta = self.db.tags.find(search_query)

            for potential_tag in tag_meta:
                tags.append(potential_tag['tagID'])

        to_search = {'tags': {'$in': tags}}

        if rating != 'any':
            to_search['rating'] = rating

        if author != 'any':
            to_search['userID'] = str(author)

        images = self.db.images.find(to_search).sort(sort_by, -1).skip(skips).limit(page_size)
        number_images = 0
        if count:
            
            number_images = self.db.images.count(to_search)

        return {'images': images, 'search_query': to_search, 'evaluated_tags': tags, 'image_count': number_images}

    def search_items(self, tag_names=[], rating='any', user='any', sort_by='uploaded_at', page_number=1, page_size=20, count=False, return_dict=False):
        skips = page_size * (int(page_number ) - 1)
        tags = []
        is_collection = False
        for tag in tag_names:
            if tag == 'is_collection':
                is_collection = True
            else:
                if ':' not in tag:
                    tag_meta = self.db.tags.find({'internal_name': tag.lower()})
                else:
                    type, name = tag.lower().split(':')
                    search_query = {'internal_name': name.lower(), 'type': type}
                    if '(' in name and ')' in name and type == 'character':
                        # we have a fandom to search by
                        search_query['fandom_internal'] = name.split('(')[1].split(')')[0].lower()
                        search_query['internal_name'] = name.split('(')[0]

                    tag_meta = self.db.tags.find(search_query)

                for potential_tag in tag_meta:
                    tags.append(potential_tag['tagID'])



        to_search = {}
        if tags:
            to_search['tags'] = {'$all': tags}

        if rating != 'any':
            to_search['rating'] = rating

        if user != 'any':
            to_search['userID'] = str(author)

        images = []
        if not is_collection:
            images = list(self.db.images.find(to_search).sort(sort_by, -1).skip(skips).limit(page_size))

        items = images

        collections = list(self.db.collections.find(to_search).sort(sort_by, -1).skip(skips).limit(page_size))
        items += collections

        items = sorted(items, key = lambda i: i['uploaded_at'], reverse=True)[:page_size]

        if return_dict:
            return {'results': items, 'search_query': to_search, 'evaluated_tags': tags}
        else:
            return items

    def get_index_of_image(self, collection, fileID):
        for i, image in enumerate(collection['images']):
            if fileID == image:
                return i
        else:
            return None

    def count_images(self, tags):
        """
        Counts the images in the database with the tags
        provided
        """
        tags = [str(x) for x in tags if x]

        query = self.db.images.count({'tags': {'$all': tags}})
        return query

    def delete_image(self, fileID):
        """
        Removes a image from either storage system
        """
        image_meta = self.db.images.find_one({'fileID': fileID})
        if image_meta.get('location', 'gridFS') == 'gridFS':
            self.grid_storage.delete(fileID + '_thumb')
            self.grid_storage.delete(fileID)
        else:
            self.spaces.delete_object(Bucket=self.config.spaces.bucket_name, Key=str(image_meta['userID']) + '/' + fileID + '.png')
            self.spaces.delete_object(Bucket=self.config.spaces.bucket_name, Key=str(image_meta['userID']) + '/' + fileID + '_thumb.png')
    
        self.logger.info('Deleting file {} from {}'.format(fileID, image_meta.get('location', 'gridFS')))

    def get_image_views(self, fileID):
        image = self.db.images.find_one({'fileID': fileID})
        return len(image['views'])

    def get_author_views(self, userID):
        images = self.get_images(author=userID)
        views = 0
        for img in images:
            views += len(img['views'])
        return views

    def set_image_views(self, fileID, remote_addr):
        image = self.db.images.find_one({'fileID': fileID})
        meta_string = hashlib.sha224(str(remote_addr).encode()).hexdigest()
        if meta_string not in image['views']:
            db.db.images.update_one({'fileID': fileID}, {'$push': {'views': meta_string}})
            return len(image['views']) + 1
        else:
            return len(image['views'])

    def get_page_count(self, image_count, page_size=20):
        return image_count % page_size

    def get_popular_tags(self, limit=10):
        return self.db.tags.find().sort('searches', -1).limit(limit)

    def get_tag(self, tag, search_by='tagID'):
        if search_by == 'tagID':
            x = self.db.tags.find_one({'tagID': str(tag)})
            return x
        else:
            return self.db.tags.find_one({search_by: tag})
        
    def get_tags_string(self, tag_list):
        output = []
        for tagID in tag_list:
            tag = self.get_tag(tagID)
            if tag:
                output.append('{} ({})'.format(tag['name'],tag['type']))

        return ', '.join(output)

    def like_tag(self, tagID, userID):
        like_mash = hashlib.sha224(str(userID).encode()).hexdigest()
        tag_meta = self.get_tag(tagID)
        print(tag_meta)
        if tag_meta:
            if not like_mash in tag_meta.get('likes', []):
                db.db.tags.update_one({'tagID': tagID}, {'$push': {'likes': like_mash}})

    def unlike_tag(self, tagID, userID):
        like_mash = hashlib.sha224(str(userID).encode()).hexdigest()
        tag_meta = self.get_tag(tagID)
        if tag_meta:
            if like_mash in tag_meta.get('likes', []):
                index = tag_meta['likes']
                db.db.tags.update_one({'tagID': tagID}, {'$pull': {'likes': like_mash}})

    def check_tag_like(self, tagID, userID):
        if not userID:
            return False

        like_mash = hashlib.sha224(str(userID).encode()).hexdigest()
        tag_meta = self.get_tag(tagID)
        if tag_meta:
            if like_mash in tag_meta.get('likes', []):
                return True
            else:
                return False

    def check_collections_for_image(self, fileID):
        return db.db.collections.find_one({'images': {'$all': [fileID]}})

    def make_id(self, length=18):
        return str(''.join([str(secrets.choice(range(0,9))) for _ in range(0,length)]))

    def make_token(self, length):
        return secrets.token_urlsafe(length)

    def make_word_token(self, word_count=4):
        output = []
        words = open('static/words.txt', 'r').readlines()

        for _ in range(0, word_count):
            output.append(secrets.choice(words).replace('\n','').title())

        return self.make_url_safe(''.join(output).encode().decode())

    def make_url_safe(self, string, safe=''):
        illegal_chars = ["'",";", "%", "#", "/", "?", "+", " "]
        for char in illegal_chars:
            string = string.replace(char, safe)
        return string

    def make_internal_name(self, to_change, safe='_'):
        """
        Change the input string to fit the internal name scheme
        aka, remove spaces, lower all characters
        """
        to_change = to_change.lower()
        to_change = self.make_url_safe(to_change, safe=safe).lower()
        print(to_change)
        return to_change
    
    # permissions
    def get_role(self, roleID):
        if not roleID:
            return ROLES['user']
        try:
            int(roleID)
        except:
            return ROLES[roleID]
        else:
            r = db.db.roles.find_one({'roleID': roleID})
            return self.wrap_permissions(name=r['name'], **r['permissions'])

    def wrap_permissions(self, **kwargs):
        return Permissions(**kwargs)

    
try:
    db = db
except:
    db = DataBase()