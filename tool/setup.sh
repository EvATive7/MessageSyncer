#!/bin/bash
no_dev=false
for arg in "$@"; do
    case $arg in
    --no-dev)
        no_dev=true
        ;;
    esac
done

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

if [ "$no_dev" = false ]; then
    git update-index --assume-unchanged src/test.py
    pre-commit install
fi
