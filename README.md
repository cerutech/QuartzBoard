# Quartz
Project Quartz. The Next Generation Image Board

## What you need
You need a MongoDB as the server uses this as the database of choice. The server also uses gridFS to store images inside of said database so you need to make sure it is either local or fast and has lots of storage to keep the files in the database. 

To set up a MongoDB instance you should follow the guide on [their website](https://docs.mongodb.com/manual/installation/).

#### S3 Support?
If you are feeling like you can afford such a thing, Quartz supports using S3 like CDN's insted of the GridFS system. This feature is still being worked on but it does work with the Digital Ocean Spaces CDN. 

## Running the server

Linux / MacOS:
```
bash run.sh
```
Windows:
```
run.bat
```
 
