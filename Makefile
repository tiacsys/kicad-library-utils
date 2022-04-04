.PHONY: help
help:
	@echo "Supported targets:"
	@echo "    lint            - verify code style"
	@echo "    style           - apply automatic formatting"
	@echo


.PHONY: lint
lint:
	python3 -m flake8 .


.PHONY: style
style:
	python3 -m isort .
	black .
