FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml ./
# Dependências lidas do pyproject (fonte única), sem instalar o pacote
RUN python -c "import tomllib;print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/req.txt \
    && pip install --no-cache-dir -r /tmp/req.txt
COPY . .
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
# exec: uvicorn passa a PID 1 e recebe o SIGTERM
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port 8000"]
