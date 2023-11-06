
.PHONY: test

build:
	mkdir -p build

build/test:
	kikit present boardpage --help


clean:
	rm -rf build

