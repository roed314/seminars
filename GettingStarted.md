Installation
============

The `seminars` codebase is based on the [LMFDB](https://github.com/LMFDB/lmfdb) and includes it as a submodule, so the installation is similar to that project.  In particular, take the following steps to get a copy up and running locally on your machine.  After creating an account on [Github](https://github.com/join) and [uploading ssh keys](https://help.github.com/en/github/authenticating-to-github/adding-a-new-ssh-key-to-your-github-account) there, do the following on your machine.  You need to have [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git), [postgresql](https://www.postgresql.org/download/) and [sage](http://www.sagemath.org/download-source.html) installed.  Note that the copy of sage should be at least version 8.6, must be built with [openssl support](http://doc.sagemath.org/html/en/installation/source.html#libraries) and must currently be installed from source, though there is [work](https://trac.sagemath.org/ticket/29158) on removing that requirement).  Note that you can skip that `sage i-` and `sage -pip` commands below if you already have LMFDB functional on your machine.

```
$ git clone git@github.com:roed314/seminars.git
$ cd seminars
$ git submodule init
$ git submodule update
$ cd lmfdb
$ sage -i gap_packages
$ sage -pip install -r requirements
```

You should then edit `seminars/lmfdb/config.ini` and change the port from `37777` to `37778` (to prevent clashes with a copy of the actual LMFDB running on your machine).  You may also want to change `default=False` to `default=True`.  After this, you can start a webserver locally by running the following in the top level seminars folder.

```
$ sage -python start-seminars.py --debug
```