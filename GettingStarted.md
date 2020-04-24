Installation
============

The `seminars` codebase is based on the [LMFDB](https://github.com/LMFDB/lmfdb) and includes it as a submodule, so the installation is similar to that project.  In particular, take the following steps to get a copy up and running locally on your machine.  After creating an account on [Github](https://github.com/join) and [uploading ssh keys](https://help.github.com/en/github/authenticating-to-github/adding-a-new-ssh-key-to-your-github-account) there, do the following on your machine.  You need to have [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git), [postgresql](https://www.postgresql.org/download/) installed.

```
$ git clone git@github.com:roed314/seminars.git
$ cd seminars
$ git submodule init
$ git submodule update
$ pip install -r requirements.txt
```

You can host a local version of the site by running the following in the top
level seminars folder --- though this may raise an error at first.

```
$ python start-seminars.py --debug
```

Doing this will create the file `seminars/lmfdb/config.ini`. If you want to
prevent clashes with a copy of the actual LMFDB running on your machine, you
should edit `seminars/lmfdb/config.ini` and change the port from `37777` to
`37778`. You may also want to change `default=False` to `default=True` in debug.

To run a local copy, it is necessary to have a background ssh port forwarding to
MIT. Assuming you have an account on legendre, you can set this up with

```
ssh -L 5432:grace:5432 legendre
```
Note that you can add this to your ssh-config file by adding the line
```
  LocalForward localhost:5432 grace:5432
```
in the appropriate place.

Then you should edit the postgresql host to `localhost` instead of
`devmirror.lmfdb.xyz` in `seminars/lmfdb/config.ini`.

After this, you can start a webserver locally by running the following in the
top level seminars folder and no errors should be raised.

```
$ python start-seminars.py --debug
```
