run-test-mode:
	TEST_MODE=1 fastapi dev --no-reload
run-light-test-mode:
	TEST_MODE=1 LIGHT_NODE=1 fastapi dev --no-reload