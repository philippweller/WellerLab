# WellerLab Orange3 add-on — one distribution, one Orange category.
# `make test` is the canonical entry point; run_tests.py locates Orange's own
# Python itself, so any python3 can drive it.

PY ?= python3

.PHONY: test dist clean icons

test:                      ## run all headless test suites (offscreen Qt)
	$(PY) run_tests.py

icons:                     ## regenerate the icon set from the shared template
	$(PY) tools/gen_icons.py

dist:                      ## build sdist + wheel into dist/
	$(PY) setup.py -q sdist bdist_wheel

clean:                     ## remove build artefacts
	rm -rf build dist *.egg-info
