FROM python:3.12-slim AS local

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend backend
COPY frontend frontend
COPY sample_data sample_data
COPY rag_data rag_data
COPY .env.example .env.example

EXPOSE 5000
CMD ["python", "-m", "backend.app"]


FROM public.ecr.aws/lambda/python:3.12 AS lambda

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR ${LAMBDA_TASK_ROOT}

COPY backend/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY backend backend
COPY frontend frontend
COPY sample_data sample_data
COPY rag_data rag_data
COPY .env.example .env.example

CMD ["backend.lambda_handler.handler"]
