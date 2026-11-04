.PHONY: test test-known-limitation test-all replay

# The green suite: every test that is expected to pass.
test:
	python3 -m unittest discover -s tests -p 'test_*.py' -v

# The one test that is expected to FAIL. Its failure is the point; read the
# annotations in tests/known_limitation_test.py.
test-known-limitation:
	@echo "----- The following test FAILS BY DESIGN (see tests/known_limitation_test.py) -----"
	-python3 -m unittest tests.known_limitation_test -v

# Both, in that order. Exit status is that of the green suite.
test-all: test test-known-limitation

replay:
	python3 replay.py
