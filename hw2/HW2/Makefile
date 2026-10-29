PYTHON ?= python3
P4C ?= p4c-bm2-ss

.PHONY: all build test run report package
all: build test
build:
	mkdir -p build
	$(P4C) --std p4-16 -o build/multipath.json p4/multipath.p4
test:
	$(PYTHON) -m unittest discover -s tests -v
run: build
	sudo -E "$(shell command -v $(PYTHON))" scripts/run.py --mode all
report:
	$(PYTHON) scripts/report.py
package: report
	$(PYTHON) scripts/package.py
