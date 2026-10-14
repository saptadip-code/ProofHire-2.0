# Render static site settings (Part C1 / C6)

Owner of render.yaml is Member 4; add these to the static-site service:

```yaml
- type: web
  name: proofhire-web
  runtime: static
  rootDir: frontend
  buildCommand: npm ci && npm run build
  staticPublishPath: dist
  envVars:
    - key: VITE_API_BASE_URL   # public build-time value: backend URL + /api/v1
      sync: false
  routes:
    - type: rewrite            # client-side routes: /* -> /index.html
      source: /*
      destination: /index.html
```

`npm ci` needs a committed `package-lock.json`. Create it once on a machine with npm access (`npm install`) and commit it.
