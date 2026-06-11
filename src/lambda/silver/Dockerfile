FROM public.ecr.aws/lambda/python:3.12

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY handler.py transforms.py reader.py writer.py ./

CMD ["handler.lambda_handler"]
