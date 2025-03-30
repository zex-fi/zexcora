run-cora:
	uv run uvicorn --no-access-log --host=127.0.0.1 --port=15782 app.main:app

run-state-manager:
	cd state_manager && uv run uvicorn --host=127.0.0.1 --port=15783 main:app

run-event-distributor:
	cd event_distributor && uv run uvicorn --host=127.0.0.1 --port=15784 main:app

run-websocket-service:
	cd websocket_service && uv run uvicorn --host=127.0.0.1 --port=15785 main:app
# Target to run the application in test mode
run-test-mode:
	python app/main.py config-test.yaml

# Target to install dependencies on macOS
install-dependencies-macos:
	@OS=$(shell uname -s); \
	if [ "$$OS" != "Darwin" ]; then \
		echo "This Makefile target is only for macOS"; \
		exit 1; \
	fi

	# Check if Homebrew is installed
	if ! command -v brew >/dev/null 2>&1; then \
		echo "Homebrew not found. Installing Homebrew..."; \
		/bin/bash -c "$$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"; \
		echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zshrc; \
		eval "$(/opt/homebrew/bin/brew shellenv)"; \
	else \
		echo "Homebrew is already installed."; \
	fi

	# Install required packages
	brew install pkg-config secp256k1 gcc gmp

	# Install Xcode Command Line Tools
	xcode-select --install || true

	# Install Automake
	curl -O http://ftp.gnu.org/gnu/automake/automake-1.16.tar.gz
	tar -xzf automake-1.16.tar.gz
	cd automake-1.16 && ./configure --prefix=/usr/local && make && sudo make install
	rm -rf automake-1.16.tar.gz automake-1.16

	# Clone and build the mcl library
	git clone https://github.com/herumi/mcl
	cd mcl && mkdir build && cd build && cmake .. && make -j$$(sysctl -n hw.ncpu) && sudo make install
	rm -rf mcl

# Target to install dependencies on Linux
install-dependencies-linux:
	@OS=$(shell uname -s); \
	if [ "$$OS" != "Linux" ]; then \
		echo "This Makefile target is only for Linux"; \
		exit 1; \
	fi

	# Update package list and install required packages
	sudo apt update && sudo apt install -y \
		pkg-config \
		libsecp256k1-dev \
		build-essential \
		gcc \
		libgmp-dev \
		automake \
		cmake \
		git

	# Clone and build the mcl library
	git clone https://github.com/herumi/mcl
	cd mcl && mkdir build && cd build && cmake .. && make -j$$(nproc) && sudo make install
	rm -rf mcl
