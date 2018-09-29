import io
import sys
import threading
from PIL import Image, ImageFont
from .database import db

class ImageUtils():
    def thumbnail(self, image, width=256):
        """
        Generate thumbnail from a raw image

        Returns BytesIO object
        (Easier for the API to deal with)
        """
        bio = io.BytesIO()
        img = Image.open(image)

        # image resize logic here
        wpercent = (width/float(img.size[0]))
        hsize = int((float(img.size[1])*float(wpercent)))
        img = img.resize((width,hsize), Image.ANTIALIAS)
        # save the image and decode to bytes
        img.save(bio, format='PNG')
        bio.seek(0)
        return bio

    def upload(self, image_bytes, fileID, author, location='gridFS'):
        """
        Uploads the image bytes to the CDN defined in location.
        """
        try:
            try:
                image_bytes.read
            except:
                image_bytes = io.BytesIO(image_bytes)

            image_bytes.seek(0)

            if db.flags['no_s3'] or location == 'gridFS':
                # is if the S3 config is not present, we just use GridFS
                # otherwise, check the location
                location = 'gridFS'
                with db.grid_storage.new_file(_id=fileID) as fp:
                    fp.write(image_bytes)

                db.logger.debug('Saving image {} to gridFS (no s3 config set)'.format(fileID))

            elif location == 's3':
                db.spaces.put_object(ACL='public-read',
                                     Bucket=db.config.spaces.bucket_name,
                                     Body=image_bytes,
                                     Key=str(author) + '/' + fileID + '.png',
                                     ContentType='image/png')
                db.logger.debug('Saving image {} to S3'.format(fileID))
            else:
                raise TypeError('Location does not exist!!')

        finally:
            image_bytes.close()

    def upload_async(self, *args, **kwargs):
        threading.Thread(None, target=self.upload, args=args, kwargs=kwargs).start()

    def upload_to_quartz(self, image_bytes, fileID, author):
        """
        Upload the image bytes to QuartzBoard.
        This is different to self.upload as this function will
        automagicly create the thumbnail and any other metadata required
        for viewing in QuartzBoard. 

        If the size is more than 1mb, the server will try to upload to the S3 CDN.
        """
        # first, we commit the image to the database
        # this will allow us to access it for thumbnail creation
        # inside a thread
        try:
            image_bytes.read
        except:
            image_bytes = io.BytesIO(image_bytes)

        image_bytes.seek(0)

        size = sys.getsizeof(image_bytes)

        db.logger.debug('Image {} is {}MB'.format(fileID,
                                                  size))
        if size > (1 * 1024 * 1024): # 1MB
            location = 'S3'
        else:
            location = 'gridFS'

        if db.config.get('force_location'):
            # allow for force location setting
            location = db.config.get('force_location', 'gridFS')

        # convert image to PNG
        try:
            img = Image.open(image_bytes)
            width, height = img.size
            bio = io.BytesIO()
            img.save(bio, format='PNG')
            bio.seek(0)

            # upload to database
            self.upload(bio, fileID, author, location=location)

            # now we do the thumbnail
            thumbnail = self.thumbnail(image_bytes, width=128) # only use the pixels that we are using for the home page
            # step 1 of image optimisation: only the the data you need
            # dont oversize the image if you do not plan to make the showing size bigger

            self.upload_async(thumbnail, fileID + '_thumbnail', author, location=location)
            db.logger.info('Saving image thumbnail {} to {}'.format(fileID, location))

            # now we work out the flags of the database
            db.db.images.update_one({'fileID': fileID}, {'$set': {'processing': False,
                                                                  'location': location}})

        finally:
            #image_bytes.close()
            #bio.close()
            # image objects are closed inside the thread.
            # Dont ask me how they reach this scope but when i try to close, they are already closed so
            # i presume it worked???
            # lmao, pythons weird sometimes
            pass

    def get_rating(self, rating):
        rating_2_external = {'e': 'Explicit',
                             'm': 'Mature',
                             None: 'Err', # default for any images that were created before i added this system
                             }
        return rating_2_external[rating]