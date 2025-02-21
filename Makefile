SPELLING_PATHS = $(wildcard *.md) docs src common klc-check test tools packages3d symbol-generators
SPELLING_EXCLUDE_FILE = .codespell-excludes
SPELLING_IGNORE_WORDS_FILE = .codespell-ignore-words
SPELLING_SKIP_FILENAMES = .mypy_cache *.csv stm32_generator.py


.PHONY: help
help:
	@echo "Supported targets:"
	@echo "    lint                - verify code style"
	@echo "    spelling            - check spelling of text"
	@echo "    style               - apply automatic formatting"
	@echo "    test-klc-footprints - test footprint KLC rule checks"
	@echo "    test-klc-symbols    - test symbol KLC rule checks"
	@echo "    check               - run all checks and tests"
	@echo


.PHONY: lint
lint:
	python3 -m flake8 .


.PHONY: spelling
spelling:
	codespell \
		--exclude-file "$(SPELLING_EXCLUDE_FILE)" \
		--ignore-words "$(SPELLING_IGNORE_WORDS_FILE)" \
		--ignore-regex='[A-Za-z0-9+/]{70,}' \
		$(patsubst %, --skip="%",$(SPELLING_SKIP_FILENAMES)) \
		$(SPELLING_PATHS)


.PHONY: style
style:
	python3 -m isort .
	black .

.PHONY: style-check 
style-check:
	python3 -m isort --check-only . 
	black --check .


.PHONY: test-klc-footprints
test-klc-footprints:
	python3 klc-check/check_footprint.py \
		--unittest \
		klc-check/test_footprint.pretty/*__*.kicad_mod

	python klc-check/check_footprint.py -vv \
		klc-check/test_footprint.pretty/SO-8_3.9x4.9mm_P1.27mm.kicad_mod


.PHONY: test-klc-symbols
test-klc-symbols:
	python3 klc-check/check_symbol.py \
	--unittest \
	klc-check/test_symbol/*.kicad_sym

# Compare the libraries in the test_symbol directory to make sure comparelibs.py works
# We do all the checks, but we exclude S5.1 because there are no footprints in this repo.
# We also discard the 2 and 3 return codes, because we don't actually care if the library
# is KLC compliant or not.
.PHONY: test-comparelibs-symbols
test-comparelibs-symbols:
	python3 klc-check/comparelibs.py -v \
		--old klc-check/test_symbol/comparelibs_old/* \
		--new klc-check/test_symbol/comparelibs_new/* \
		--check --check-derived \
		--junit junit-comparelibs.xml \
		--exclude S5.1 \
		--metrics || if [ $$? -eq 2 ] || [ $$? -eq 3 ] ; then true; fi

.PHONY: check
check: lint spelling test-klc-footprints test-klc-symbols test-comparelibs-symbols

.PHONY: install-deps
install-deps:
	pip3 install -r requirements.txt
