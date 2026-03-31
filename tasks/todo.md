## Remaining Launch Setup - March 18, 2026

### Plan
- [x] Stripe setup — Create products/prices, add keys to .env
- [x] Zep API key — Added to .env
- [x] Redis — Installed locally (C:\redis), running on port 6379
- [x] Login redirect fix — LoginView.vue now respects ?redirect param
- [x] CORS fix — Added port 3001 to CORS_ORIGINS
- [x] Stripe webhook — Created endpoint, secret added to .env
- [x] Welcome email — Updated to match free tier (no free credit)
- [x] Production Docker config — Updated nginx.conf with SSL, docker-compose.prod.yml with certbot
- [x] Deployment script — deploy.sh created
- [x] Production .env template — .env.production created
- [ ] **Manual: Buy glasinsight.com domain** (Namecheap, Cloudflare, or Google Domains)
- [ ] **Manual: Sign up for Resend** (resend.com) and add API key to .env
- [ ] **Manual: Get a VPS** (Hetzner CX22 recommended, ~$5/mo)
- [ ] **Manual: Deploy** using deploy.sh
- [ ] **Manual: Set ADMIN_USER_IDS** after signing up on the platform
- [ ] **Manual: Switch Stripe to live mode** when ready to charge real money

### Notes
- Stripe is in TEST mode (sk_test_). When ready for real payments, create live products in Stripe and update keys
- Stripe webhook endpoint is registered at glasinsight.com/api/billing/webhook
- Redis installed at C:\redis\redis-server.exe (Windows port v5.0.14.1)
- Docker Desktop was installed but daemon wouldn't start — Redis installed natively instead
- Resend email service gracefully skips if not configured
- Supabase auth redirect URLs need to be updated in Supabase dashboard when going to production

### Review
- All code changes completed successfully
- Backend starts clean with all services configured
- Frontend running on port 3001, backend on 5001
- All Stripe products/prices created in test mode
- Production Docker setup ready with SSL/certbot
