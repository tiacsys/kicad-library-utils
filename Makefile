.PHONY: help
help:
	@echo "Supported targets:"
	@echo "    style           - apply automatic formatting"
	@echo


.PHONY: style
style:
	python3 -m isort .
	black .
