FROM python:3.14-slim

WORKDIR /app

COPY ./ .

# Install the application and its runtime dependencies from pyproject.toml.
RUN pip install --upgrade pip && \
    pip install .

EXPOSE 8088

CMD ["python", "main.py"]
