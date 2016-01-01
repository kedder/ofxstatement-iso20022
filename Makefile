PYTHON=.venv/bin/python

all: .venv/bin/ofxstatement

.venv:
	virtualenv -p python3 --no-site-packages .venv

.venv/bin/ofxstatement: .venv setup.py
	$(PYTHON) setup.py develop
