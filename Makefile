# WellerLab monorepo.
#
# The whole Orange tool suite now lives in orange-wellerlab-addon/ (one
# distribution, one category "Weller Lab"); the historical per-tool folders are
# kept for reference only. These targets delegate there, so the repo has a
# conventional entry point at its root.

PY ?= python3
ADDON := orange-wellerlab-addon

.PHONY: test install icons widgets workflows dist clean

test:                       ## run every test suite (headless, 6 suites)
	$(MAKE) -C $(ADDON) test

install:                    ## install the suite into Orange's own Python
	$(PY) orange-install.py wellerlab

icons:                      ## regenerate the shared icon set
	$(MAKE) -C $(ADDON) icons

widgets:                    ## regenerate WIDGETS.md (widget overview)
	$(MAKE) -C $(ADDON) widgets

workflows:                  ## regenerate the example workflows (examples/*.ows)
	$(MAKE) -C $(ADDON) workflows

dist:                       ## build sdist + wheel
	$(MAKE) -C $(ADDON) dist

clean:                      ## drop build artefacts
	$(MAKE) -C $(ADDON) clean
