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
		$(patsubst %, --skip="%",$(SPELLING_SKIP_FILENAMES)) \
		$(SPELLING_PATHS)


.PHONY: style
style:
	python3 -m isort .
	black .


.PHONY: test-klc-footprints
test-klc-footprints:
	python klc-check/check_footprint.py \
		--unittest \
		klc-check/test_footprint.pretty/*__*.kicad_mod


.PHONY: test-klc-symbols
test-klc-symbols:
	python klc-check/check_symbol.py \
	--unittest \
	klc-check/test_symbol/*.kicad_sym


.PHONY: check
check: lint spelling test-klc-footprints test-klc-symbols

.PHONY: install-deps
install-deps:
	pip install -r requirements.txt
