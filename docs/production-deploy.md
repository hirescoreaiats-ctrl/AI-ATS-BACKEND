# Production Deploy Notes

Use Git as the source of truth for production changes. Do not start multiple manual backend processes while a systemd service or another uvicorn process is already active.

```bash
cd /var/www/hirescore-ai-backend
git pull origin production-scoring-v2

pkill -f "uvicorn backend.main:app" || true
sleep 3

nohup /var/www/hirescore-ai-backend/venv/bin/uvicorn backend.main:app --host 0.0.0.0 --port 8000 --workers 1 > backend.log 2>&1 &
sleep 5

ps aux | grep uvicorn | grep -v grep
ss -ltnp | grep :8000
curl http://127.0.0.1:8000/api/v1/health
curl http://127.0.0.1:8000/api/v1/health/ready
```

Expected after deploy:

- Only one backend worker/process group.
- Port 8000 listening.
- Health ok.
- Database ready.
- Dashboard shows real data or a clear error, never fake zero stats from a failed database request.

If a systemd service is configured, prefer:

```bash
systemctl daemon-reload
systemctl enable hirescore-ai-backend
systemctl restart hirescore-ai-backend
```

Do not use `nohup` manually while the systemd service is active.
