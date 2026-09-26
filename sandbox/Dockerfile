# Sandbox für LLM-generierten Code
FROM python:3.11-slim
RUN pip install --no-cache-dir pandas numpy matplotlib scipy
RUN useradd -m runner
USER runner
WORKDIR /work
ENV MPLBACKEND=Agg
