FROM python:3.12-slim

WORKDIR /app

COPY server.py matrix.py matrix_0002.py catalogue.py catalogue_0002.py patients.py pdf_extract.py ./
COPY app ./app
COPY cache ./cache
COPY data ./data
COPY ["07_Stationaerer_Patientenbrief_2021-11-12 (1)", "07_Stationaerer_Patientenbrief_2021-11-12 (1)"]

ENV PORT=8080
EXPOSE 8080

CMD ["python3", "-u", "server.py"]
