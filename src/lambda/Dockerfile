FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py extraction.py db_connection.py s3_writer.py watermark.py ./

CMD ["handler.lambda_handler"]
