# glasinsight.com

The folder `glasinsight/` is the source of the static landing page at <https://glasinsight.com>.
It is two hand-written HTML pages and two images. There is no build step.

| File | Served at |
|---|---|
| `index.html` | `/` |
| `report.html` | `/report` (Cloudflare Pages drops `.html` and redirects `/report.html` to `/report`) |
| `glas-logo.png`, `favicon.png` | `/glas-logo.png`, `/favicon.png` |

Until 2026-11-05 these files were not in any repository. They were uploaded straight to the
Cloudflare Pages project `glasinsight` (`glasinsight.pages.dev`). They were copied into this
folder from the live site on that date, then edited.

## Deploy

No workflow deploys it. Keep this README outside `glasinsight/`, or it is published too. This repository has no Cloudflare secret. Deploy by hand with a
Cloudflare API token that can edit Pages:

```powershell
$env:CLOUDFLARE_API_TOKEN = '<token>'   # Cloudflare account that owns glasinsight.com
npx wrangler@4 pages deploy site/glasinsight --project-name=glasinsight --branch=main
```

Then check <https://glasinsight.com> and <https://glasinsight.com/report>.

## Rules for the text

- Glas Intelligence is "a Shiloh Consulting product". Link <https://shilohconsulting.ie>.
- Do not present any output as a forecast. No accuracy number exists yet.
- The sample report is recorded engine output. Do not rewrite it. The note above it says that it
  is simulated, and that the real organisations named in it are simulated personas.
