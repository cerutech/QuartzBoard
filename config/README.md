## What are these files?
These config files are different to the one in the root directory because these are critical to the site running perfectly.
The site needs role_defaults.json to set up the basic permissions for anon users. If this is not set correctly, you run the risk of letting anon users ruin your site.

It is best to leave this file **ALONE**. Please use the route `/admin/roles` for setting up roles. Only users with `edit_roles` permissions may edit roles (Obviously).
To get started, ask the site owner to create a role with the required permissions