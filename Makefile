SPELLING_PATHS = $(wildcard *.md) docs src common klc-check .v5_schlib test tools packages3d symbol-generators
SPELLING_EXCLUDE_FILE = .codespell-excludes
SPELLING_IGNORE_WORDS_FILE = .codespell-ignore-words
SPELLING_SKIP_FILENAMES = .mypy_cache


.PHONY: help
help:
	@echo "Supported targets:"
	@echo "    lint            - verify code style"
	@echo "    spelling        - check spelling of text"
	@echo "    style           - apply automatic formatting"
	@echo


.PHONY: lint
lint:
	python3 -m flake8 .


.PHONY: spelling
spelling:
	codespell \
		--exclude-file "$(SPELLING_EXCLUDE_FILE)" \
		--ignore-words "$(SPELLING_IGNORE_WORDS_FILE)" \
		--skip "$(SPELLING_SKIP_FILENAMES)" \
		$(SPELLING_PATHS)


.PHONY: style
style:
	python3 -m isort .
	black .
