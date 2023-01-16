FROM python:3.8

ENV PYTHONPATH=/dirdiff
WORKDIR /dirdiff

COPY requirements* ./

RUN for req in requirements*.txt; do pip install -r "${req}"; done

COPY . ./
