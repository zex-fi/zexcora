run-cora:
	uv run uvicorn --no-access-log --host=127.0.0.1 --port=15782 app.main:app

run-state-manager:
	cd state_manager && uv run uvicorn --host=127.0.0.1 --port=15783 main:app

run-event-distributor:
	cd event_distributor && uv run uvicorn --host=127.0.0.1 --port=15784 main:app

run-websocket-service:
	cd websocket_service && uv run uvicorn --host=127.0.0.1 --port=15785 main:app
