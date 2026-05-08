# MIP solver image — opt-specialists discipline
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ADDITIONAL_OUTPUT_DIR=/workspace/additional_output

WORKDIR /workspace
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Build-time smoke check
RUN python -c "from qcentroid import solver; from synthetic import generate_small; \
    out = solver(generate_small(), max_exec_time_m=1); \
    assert out['result']['solution_status'] in ('optimal','feasible','feasible_time_limit'), out"

CMD ["python", "qcentroid.py"]
