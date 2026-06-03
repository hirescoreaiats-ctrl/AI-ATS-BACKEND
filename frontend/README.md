# HireScore AI Frontend

Frontend for HireScore AI.

This repo contains the current legacy static dashboard plus the React/Vite migration entrypoint.

## Main Production Entry

Use `index.html` as the main entry for hosting today.

Recommended static hosts:

- Vercel static project
- Netlify
- Cloudflare Pages
- Nginx static hosting

## Connect to Backend

Edit `runtime-config.js` before deployment:

```js
window.__HIRESCORE_API_BASE__ = "https://your-backend-domain.com";
```

That backend URL should point to your DigitalOcean VPS API.

## Important Pages

- `index.html` - recruiter dashboard
- `login.html` - recruiter login
- `Signup.html` - signup
- `pricing.html` - pricing
- `apply.html` - public candidate apply page
- `candidate-tracking.html` - candidate status tracking
- `ai_explanation.html` - AI candidate report

## Optional React Build

The React migration starts at `enterprise.html`.

```bash
npm install
npm run build
```

For today's hosting, deploy the static root directly unless you specifically want the React migration.

## GitHub Push

```bash
git init
git add .
git commit -m "Initial frontend repo"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/hirescore-frontend.git
git push -u origin main
```
