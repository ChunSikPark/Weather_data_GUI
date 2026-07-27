# Frontend

Plain HTML/CSS/JS — no build step required.

## Local Development

```bash
cd frontend
python -m http.server 3000
# Open http://localhost:3000
```

By default the frontend calls `window.location.origin` for API requests (i.e., same host). To point it at a different backend, set `window.API_BASE` before the module loads:

```html
<script>window.API_BASE = 'https://your-backend.railway.app'</script>
```

This line is already present in `index.html` — just update the URL.

## Deployment (Cloudflare Pages)

1. Set **Build output directory** to `frontend` in the Cloudflare Pages project settings.
2. Leave the build command empty (no build step).
3. Edit `index.html` and set `window.API_BASE` to your Railway/Render backend URL before deploying.

If you use a Cloudflare Proxy Rule to route `/api/*` to your backend on the same domain, you can leave `window.API_BASE` as an empty string — requests will go to the same origin.
