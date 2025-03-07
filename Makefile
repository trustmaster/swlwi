# Makefile for Python project

# Variables
PYTHON = /usr/bin/env python3
LIB_DIR = swlwi
SRC_DIR = swlwi
TEST_DIR = tests

# Targets
.PHONY: ts test cover

ts:
	@echo "Building the project..."
	# For each *.py file in the examples/mylib directory run the ./flyde.py gen command to generate TS bindings
	@for file in $(LIB_DIR)/*.py; do \
		@pyflyde gen $$file; \
	done

lint:
	@echo "Running linters..."
	@black $(LIB_DIR) $(TEST_DIR);
	@flake8 $(LIB_DIR) $(TEST_DIR);

stubgen:
	@echo "Generating type stubs..."
	@rm -f $(SRC_DIR)/*.pyi;
	@stubgen $(SRC_DIR) --include-docstrings --include-private -o .;

test:
	@echo "Running tests..."
	@$(PYTHON) -m unittest discover -s $(TEST_DIR) -p "test_$(if $(mod),$(mod),*).py";

cover:
	@echo "Running tests with coverage..."
	@coverage run -m unittest discover -s $(TEST_DIR) -p "test_*.py" ;

report:
	@coverage report -m --skip-empty --omit="tests/*";

venv-activate:
	@echo "Activating virtual environment..."
	@source .venv/bin/activate;
