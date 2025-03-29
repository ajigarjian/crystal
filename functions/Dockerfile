FROM python:3.12

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt
RUN pip install pyarrow==19.0.1

COPY . .

CMD [ "python", "-m", "functions_framework", "--target=stream_analyze" ] 