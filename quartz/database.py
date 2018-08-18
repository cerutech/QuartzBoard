import secrets
import pymongo
import gridfs
import hashlib
import boto3
import json
import logging

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
            return getattr(self, key, default)
        else:
            return None
        
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

class DataBase:
    def __init__(self):
        self.db_connection = pymongo.MongoClient()

        self.db = self.db_connection.quartz

        self.grid_storage = gridfs.GridFS(self.db_connection.file_storage)

        session = boto3.session.Session()

        self.config = RecordObject(**config)
        self.logger = logging.getLogger('quartz.database')

        if not self.config.get('developer_mode'):
            self.logger.debug('Not using Developer Mode. Debug endpoints are closed.')
            self.config.set(developer_mode=False)

        # use DigitalOcean's Spaces API to handle
        # file storage

        # is interchangable with S3
        self.base_url = 'https://{}.nyc3.digitaloceanspaces.com/'.format(self.config.spaces.bucket_name)

        self.spaces = session.client('s3',
                                     region_name='nyc3',
                                     endpoint_url='https://nyc3.digitaloceanspaces.com',
                                     aws_access_key_id=self.config.spaces.access_key,
                                     aws_secret_access_key=self.config.spaces.access_private)
        print(self.config)

    def get_user(self, userID, search_by='userID', safe_mode=True):
        user = self.db.users.find_one({search_by: userID})
        if not user:
            return {}
         
        if safe_mode:
            del user['token']
            del user['password_hash']

        return user

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

        return self.grid_storage.find_one(fileID).read()

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
            return self.db_resp(self.db.images.find({'userID': int(author)}).sort(sort_by, -1).skip(skips).limit(page_size))

        if not tags:
            return self.db_resp(self.db.images.find().sort(sort_by, -1).skip(skips).limit(page_size))
        else:
            tags = [str(x) for x in tags if x]

            query = self.db.images.find({'tags': {'$all': tags}}).sort(sort_by, -1).skip(skips).limit(page_size)

        return list(query)

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
        print(tag)
        if search_by == 'tagID':
            x = self.db.tags.find_one({'tagID': str(tag)})
            print(x)
            return x
        else:
            return self.db.tags.find_one({search_by: tag})
        
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

    def make_id(self, length=18):
        return str(''.join([str(secrets.choice(range(0,9))) for _ in range(0,length)]))

    def make_token(self, length):
        return secrets.token_urlsafe(length)

    def make_word_token(self, word_count=4):
        output = []
        words = open('static/words.txt', 'r').readlines()

        for _ in range(0, word_count):
            output.append(secrets.choice(words).replace('\n','').title())

        return ''.join(output).encode().decode()

try:
    db = db
except:
    db = DataBase()
    logger.error('New instance')