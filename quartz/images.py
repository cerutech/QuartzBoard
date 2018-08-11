from .database import db

def upload_image(image_bytes, fileID):
    gridFS = db.grid_storage.new_file(_id=fileID)

    gridFS.write(image_bytes)
