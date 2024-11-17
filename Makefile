run-test-mode:
	TEST_MODE=1 BETTER_EXCEPTIONS=1 python app/main.py
run-light-test-mode:
	TEST_MODE=1 LIGHT_NODE=1 fastapi dev --no-reload

new-redis-test:
	docker stop zsequencer-redis-test; docker rm zsequencer-redis-test; sudo rm -rf redis-data-test && docker run --name zsequencer-redis-test -v $(shell pwd)/redis-data-test:/data -v $(shell pwd)/redis.conf:/redis.conf -p 7379:6379 -d redis:alpine redis-server /redis.conf

run-tests: new-redis-test
	REDIS_PORT=7379 TEST_MODE=1 BETTER_EXCEPTIONS=1 pytest -vv

