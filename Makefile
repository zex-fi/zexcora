run-test-mode:
	TEST_MODE=1 BETTER_EXCEPTIONS=1 python app/main.py
run-light-test-mode:
	TEST_MODE=1 LIGHT_NODE=1 fastapi dev --no-reload

test:
	TEST_MODE=1 BETTER_EXCEPTIONS=1 pytest