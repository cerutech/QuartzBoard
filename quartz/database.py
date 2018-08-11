import secrets
import pymongo
import gridfs
import hashlib
import boto3
import json
import logging

try:
    config = json.load(open('config.json'))
except FileNotFoundError:
    config = {}
except json.JSONDecodeError:
    logging.error('JSON config is malformed. Using default config')
    config = {}

class RecordObject():
    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._set(**kwargs)

    def get(self, key, default=None):
        if key in self.kwargs:
            return getattr(self, key, default=default)
        else:
            return None
        
    def _set(self, **kwargs):
        for k,v in kwargs.items():
            setattr(self, k, v)

    def set(self, **kwargs):
        return self._set(**kwargs)

    def __str__(self):
        s = '< '
        for item in dir(self):
            if item.startswith('__'):
                continue

            if not callable(item):
                s += '{}, '.format(str(item))

        return s + ' >'




class DataBase:
    def __init__(self):
        self.db_connection = pymongo.MongoClient()

        self.db = self.db_connection.quartz

        self.grid_storage = gridfs.GridFS(self.db_connection.file_storage)
        

        session = boto3.session.Session()

        

        self.config = RecordObject(**config)
        self.config.set(**{'use_gridfs': True})

        if not self.config.get('developer_mode'):
            logging.debug('[DB] Not using developer_mode')
            self.config.set(developer_mode=False)

        if not self.config.use_gridfs:
            # use DigitalOcean's Spaces API to handle
            # file storage
            self.base_url = 'https://{}.nyc3.digitaloceanspaces.com/'.format(self.config.spaces.bucket_name)

            self.spaces = session.client('s3',
                                         region_name='nyc3',
                                         endpoint_url='https://nyc3.digitaloceanspaces.com',
                                         aws_access_key_id=self.config.spaces.access_key,
                                         aws_secret_access_key=self.config.spaces.access_private)

    def get_user(self, userID, search_by='userID', safe_mode=True):
        user = self.db.users.find_one({search_by: userID})
        if not user:
            return {}
         
        if safe_mode:
            del user['token']
            del user['password_hash']

        return user

    def upload_image(self, image_bytes, fileID, author=None):
        if self.config.use_gridfs:
            with self.grid_storage.new_file(_id=fileID) as fp:
                fp.write(image_bytes)

        else:
            image_bytes.seek(0)
            self.spaces.put_object(ACL='public-read',
                                   Bucket=self.config.spaces.bucket_name,
                                   Body=image_bytes,
                                   Key=str(author) + '/' + fileID + '.png',
                                   ContentType='image/png')


    def get_image(self, fileID):
        #if not self.grid_storage.exists(fileID):
        #    raise TypeError('FileID does not exist')
        #    
        return self.grid_storage.find_one(fileID).read()

    def db_resp(self, resp):
        return list(resp)

    def get_images(self, tags=[], author=None, page_number=1, page_size=20):
        skips = page_size * (int(page_number ) - 1)
        if author:
            return self.db_resp(self.db.images.find({'userID': int(author)}).sort('uploaded_at', -1).skip(skips).limit(page_size))

        if not tags:
            return self.db_resp(self.db.images.find().sort('uploaded_at', -1).skip(skips).limit(page_size))
        else:
            tags = [x for x in tags if x]

            query = self.db.images.find({'tags': {'$all': tags}}).sort('uploaded_at', -1).skip(skips).limit(page_size)
        return list(query)

    def delete_image(self, fileID):
        return self.grid_storage.delete(fileID)

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
        return self.db.tags.find_one({search_by: tag})

    def make_id(self, length=18):
        return int(''.join([str(secrets.choice(range(0,9))) for _ in range(0,length)]))

    def make_token(self, length):
        return secrets.token_urlsafe(length)

    def make_word_token(self, word_count=4):
        output = []
        words = open('static/words.txt', 'r').readlines()

        for _ in range(0, word_count):
            output.append(secrets.choice(words).replace('\n','').title())

        return ''.join(output).encode().decode()



db = DataBase()