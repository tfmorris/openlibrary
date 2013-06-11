.. _bootstrap:

Setting up a dev instance
=========================

Setting up an Open Library dev instance requires installing some third-party 
software and Python modules. This document will step you though the 
installation process.

Supported Platforms
-------------------

The Open Library dev instance has been tested on the following platforms.

* Ubuntu 12.04
* Ubuntu 10.10
* Ubuntu 10.04
* Mac OS X Snow Leopard (with `XCode`_ and `homebrew`_ installed)

Make sure you have at least 1GB of RAM on your dev machine or virtual machine.

.. _XCode: http://developer.apple.com/technologies/xcode.html
.. _homebrew: http://mxcl.github.com/homebrew/

Getting the source
------------------

Open Library uses ``git`` for version control and the `code repository`_ is
hosted on github.

.. _code repository: https://github.com/internetarchive/openlibrary

If you don't have git installed, you can install it on Ubuntu using::

    $ sudo apt-get install git-core
    
and on Mac OS X using::

    $ brew install git

You can get the Open Library source code from Github using::

   $ git clone git://github.com/internetarchive/openlibrary.git
   $ cd openlibrary

This will create a directory called openlibrary with the entire
codebase checked out.

Installing dependencies
-----------------------

Open Library depends a lot of third-party programs.

To install all the dependencies::

    $ sudo ./scripts/install_dependencies.sh

Note that this is run as root.

See :doc:`appendices/dependencies` for the list of dependencies.

Setting up the dev instance
---------------------------

Once all the dependencies are installed, you are ready to setup the dev instance.

If you are running Python 2.6, the dev instance can be setup by running::

	$ make bootstrap
	
This will do the following tasks, each of which can be invoked independently using make.  

* create virtualenv (``make venv``)
* install solr (``make install_solr``)
* setup coverstore (``make setup_coverstore``)
* setup openlibrary webapp (``make setup_ol``)

If you are running Python 2.7, the first step above won't work. You should
replace ``make venv`` with ::

	$ virtualenv env
	$ env/bin/pip install -r requirements.txt

This is because Python bundle is from 2011 and one of the modules that it
includes, importlib, fails to install on Python 2.7.
http://www.archive.org/download/ol_vendor/openlibrary.pybundle

Destroying the dev instance
---------------------------

You want to destroy the current dev instance to build a new one, you can do it using::

	$ make destroy
	
Running the dev instance
------------------------

Running the dev instance requires running 2 services. Solr is run the background as daemon and the the ol webapp is run in the foreground.

The Solr processes can be started and stopped using `solr.sh` script.::

	$ ./scripts/solr.sh start
	Starting Solr
	Done. Output is logged to var/log/solr.log.
	
	$ ./scripts/solr.sh status
	Solr running with pid 97208.

	$ ./scripts/solr.sh stop
	Stopping Solr
	Done
	
	$ ./scripts/solr.sh status
	Solr is not running
	
The OL webapp can be started as::

	$ make run
	
Make sure Solr is running before starting the webapp.
	
Once the webapp is started, the website can be accessed at http://0.0.0.0:8080/.

Loading sample data
-------------------

Use the `copydocs.py` script to load sample records from openlibrary.org website.::

	$ make load_sample_data

Make sure both Solr and the webapp are running before running this.

Restart the webapp to see the books on homepage.

Known Issues
------------

It is known that the following issues exist:

* Stats on the home page is not working
* /admin is failing
* /libraries/stats is failing
* Lists are not working
* subject search is not working

Not an "issue" per se, but slightly confusing for first timers, is that some
portions of production OpenLibrary web site, such as the help pages, wiki pages
served from the database, so you won't see them in your dev instance.
