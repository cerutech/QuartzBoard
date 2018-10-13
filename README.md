<h2 align="center">
QuartzBoard
</h2> 
<h4 align="center">Version 0.6 (Ruby)</h4>
<p align="center">A new look at image boards</p>

#### Warning: This project is still in development. There will be bugs, if you find one, please be sure to let us know asap.
#### You can see the example server [here](https://quartzboard.org/)

## What you need
You need a MongoDB as the server uses this as the database of choice. The server also uses gridFS to store images inside of said database so you need to make sure it is either local or fast and has lots of storage to keep the files in the database. 

To set up a MongoDB instance you should follow the guide on [their website](https://docs.mongodb.com/manual/installation/).

## S3 Support?
If you have added S3 login details into your config.json then the server will use this for files larger than 1MB. This is to keep external costs down while also optimising the S3 CDN. The server also works with S3-like CDN's such as Digital Ocean's Spaces.

Other S3 implementations are being looked into but is confirmed to work with Digital Ocean Spaces. [Help wanted!]

## Running the server

Linux / MacOS:
```
bash run.sh
```
Windows:
```
run.bat
```

These files will make sure that your Python install is working and has the proper dependencies installed. The server will create the database and collections automaticly so that there is no problems with that side. I am currently working on a auto-setup that will allow you to create your admin account but there are currently more pressing problems to solve.

After the server is started, there shouldnt be too many problems with day-to-day use. 

## Contributing
If you have an idea that you think should be added to Quartz, you can join [our discord](https://discord.gg/Sz2qQJt) and let Cerulean#7014 know!
