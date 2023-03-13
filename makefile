# Workflows
.PHONY = clean build pypi pypi-test

## Package management
clean:
	rm -rf ./dist;
	rm -rf ./build;
	rm -rf ./*.egg-info

build: clean
	python3 setup.py sdist bdist_wheel

pypi: build
	twine upload --repository-url https://upload.pypi.org/legacy/ dist/*;

pypi-test: build
	twine upload --repository-url https://test.pypi.org/legacy/ dist/*
