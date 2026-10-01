PY ?= python3
export PYTHONPATH := src

.PHONY: test test-py test-js demo web serve lint-dash

test: test-py test-js

test-py:
	$(PY) -m unittest discover -s tests -t . -v 2>&1 | tail -n 25

test-js:
	node --test web/tests/

demo:
	$(PY) -m dopamine_king demo

web:
	$(PY) -m dopamine_king build-web

serve:
	$(PY) -m dopamine_king serve

# Project rule: the long dash character must never appear in any file.
lint-dash:
	@! grep -rIl --exclude-dir=.git --exclude-dir=node_modules $$(printf '\xe2\x80\x94') . || (echo "em dash found" && exit 1)
