# Repository Coverage

[Full report](https://htmlpreview.github.io/?https://github.com/Jott2121/graph-guard/blob/python-coverage-comment-action-data/htmlcov/index.html)

| Name                             |    Stmts |     Miss |   Cover |   Missing |
|--------------------------------- | -------: | -------: | ------: | --------: |
| graph\_guard/\_\_init\_\_.py     |        0 |        0 |    100% |           |
| graph\_guard/build\_cli.py       |       22 |        1 |     95% |        30 |
| graph\_guard/eval\_metrics.py    |       49 |        0 |    100% |           |
| graph\_guard/eval\_probes.py     |       40 |        0 |    100% |           |
| graph\_guard/extract.py          |      141 |       15 |     89% |27, 31, 37, 93-95, 133-134, 179-182, 194-196 |
| graph\_guard/fuseki.py           |       44 |        0 |    100% |           |
| graph\_guard/graph\_retriever.py |       63 |        1 |     98% |        40 |
| graph\_guard/guards.py           |       21 |        0 |    100% |           |
| graph\_guard/ontology.py         |       10 |        0 |    100% |           |
| graph\_guard/ppr.py              |       38 |        2 |     95% |     34-35 |
| graph\_guard/rdf\_export.py      |       49 |        0 |    100% |           |
| graph\_guard/reasoned\_graph.py  |       46 |        0 |    100% |           |
| graph\_guard/reasoning.py        |       13 |        0 |    100% |           |
| graph\_guard/schema.py           |       19 |        0 |    100% |           |
| graph\_guard/service.py          |       48 |        2 |     96% |     40-41 |
| graph\_guard/shacl.py            |       14 |        0 |    100% |           |
| graph\_guard/store.py            |       50 |        0 |    100% |           |
| **TOTAL**                        |  **667** |   **21** | **97%** |           |


## Setup coverage badge

Below are examples of the badges you can use in your main branch `README` file.

### Direct image

[![Coverage badge](https://raw.githubusercontent.com/Jott2121/graph-guard/python-coverage-comment-action-data/badge.svg)](https://htmlpreview.github.io/?https://github.com/Jott2121/graph-guard/blob/python-coverage-comment-action-data/htmlcov/index.html)

This is the one to use if your repository is private or if you don't want to customize anything.

### [Shields.io](https://shields.io) Json Endpoint

[![Coverage badge](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/Jott2121/graph-guard/python-coverage-comment-action-data/endpoint.json)](https://htmlpreview.github.io/?https://github.com/Jott2121/graph-guard/blob/python-coverage-comment-action-data/htmlcov/index.html)

Using this one will allow you to [customize](https://shields.io/endpoint) the look of your badge.
It won't work with private repositories. It won't be refreshed more than once per five minutes.

### [Shields.io](https://shields.io) Dynamic Badge

[![Coverage badge](https://img.shields.io/badge/dynamic/json?color=brightgreen&label=coverage&query=%24.message&url=https%3A%2F%2Fraw.githubusercontent.com%2FJott2121%2Fgraph-guard%2Fpython-coverage-comment-action-data%2Fendpoint.json)](https://htmlpreview.github.io/?https://github.com/Jott2121/graph-guard/blob/python-coverage-comment-action-data/htmlcov/index.html)

This one will always be the same color. It won't work for private repos. I'm not even sure why we included it.

## What is that?

This branch is part of the
[python-coverage-comment-action](https://github.com/marketplace/actions/python-coverage-comment)
GitHub Action. All the files in this branch are automatically generated and may be
overwritten at any moment.