.PHONY: test run-society run-colony run-connection evaluate dashboard

test:
	python -m pytest -q

run-society:
	python -m aethergrid.run --world society --scenario aethergrid/configs/worlds/society.json

run-colony:
	python -m aethergrid.run --world colony --scenario aethergrid/configs/worlds/colony.json

run-connection:
	python -m aethergrid.run --world connection --scenario aethergrid/configs/worlds/connection.json

evaluate:
	python -m aethergrid.evaluate --all

dashboard:
	streamlit run aethergrid/ui/app.py
