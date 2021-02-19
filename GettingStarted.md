Installation
============

The `seminars` codebase is based on the [LMFDB](https://github.com/LMFDB/lmfdb) and includes the common module [psycodict](https://github.com/roed314/psycodict) as a submodule, so the installation is similar to that project.  In particular, take the following steps to get a copy up and running locally on your machine.
After creating an account on [Github](https://github.com/join) and [uploading ssh keys](https://help.github.com/en/github/authenticating-to-github/adding-a-new-ssh-key-to-your-github-account) there, do the following on your machine.  You need to have [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) installed.

```
$ git clone git@github.com:roed314/seminars.git
$ cd seminars
$ git submodule init
$ git submodule update
$ pip install -r requirements.txt
```

To generate the default config file `config.ini`, run
```
$ python start-seminars.py --debug
```


You can now host a local version of the site by running the following in the top
level seminars folder.

```
$ python start-seminars.py --debug
```
