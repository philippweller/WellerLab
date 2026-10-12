# WellerLab Orange3 add-on — one distribution, one Orange category.
# `make test` is the canonical entry point; run_tests.py locates Orange's own
# Python itself, so any python3 can drive it.

PY ?= python3

.PHONY: test dist clean icons widgets workflows

test:                      ## run all headless test suites (offscreen Qt)
	$(PY) run_tests.py

icons:                     ## regenerate the icon set from the shared template
	$(PY) tools/gen_icons.py

widgets:                   ## regenerate WIDGETS.md from the widget registry
	$(PY) tools/gen_widgets_md.py

workflows:                 ## regenerate the example workflows in examples/
	$(PY) tools/make_workflows.py

dist:                      ## build sdist + wheel into dist/
	$(PY) setup.py -q sdist bdist_wheel

clean:                     ## remove build artefacts
	rm -rf build dist *.egg-info
