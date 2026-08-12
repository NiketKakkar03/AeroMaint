FROM python:3.11-slim
WORKDIR /opt/aeromaint
COPY infrastructure/local-release/profile_service.py ./profile_service.py
ENTRYPOINT ["python", "profile_service.py"]
