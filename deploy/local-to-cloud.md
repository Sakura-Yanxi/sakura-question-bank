# Local To Cloud Checklist

1. Export a Sakura backup ZIP from the local UI.
2. Deploy Sakura on the target server.
3. Set `.env` and enable login.
4. Open the cloud site and verify `/api/health`.
5. Import the backup ZIP.
6. Check documents, questions, page images, textbooks and reflection history.
7. Configure `APP_PUBLIC_URL`.
8. Configure notification channels only after the public URL works.
9. Run `python3 scripts/health_check.py`.

For a public demo server, prefer `SAKURA_DEMO_MODE=1` and do not import your real backup.
