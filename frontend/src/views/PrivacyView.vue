<template>
  <div class="privacy-page">
    <div class="privacy-container">
      <h1>Privacy Policy</h1>

      <section>
        <h2>1. Information We Collect</h2>
        <p>We collect the following categories of information:</p>
        <ul>
          <li>
            <strong>Account data:</strong> Email address and authentication
            credentials when you create an account.
          </li>
          <li>
            <strong>Simulation data:</strong> Scenarios, agent configurations,
            uploaded documents, and generated reports created through the platform.
          </li>
          <li>
            <strong>Payment information:</strong> Billing details processed
            securely through Stripe. We do not store credit card numbers on our
            servers.
          </li>
          <li>
            <strong>Usage data:</strong> Feature usage patterns and interaction
            logs to improve the service.
          </li>
        </ul>
      </section>

      <section>
        <h2>2. How We Use Your Data</h2>
        <p>Your data is used to:</p>
        <ul>
          <li>Provide, maintain, and improve the Glas Intelligence platform.</li>
          <li>Process payments and manage subscriptions.</li>
          <li>Send transactional emails (account verification, password resets, billing receipts).</li>
          <li>Respond to support requests.</li>
          <li>Generate anonymized, aggregated analytics to improve model quality.</li>
        </ul>
        <p>We do not sell your personal data to third parties.</p>
      </section>

      <section>
        <h2>3. Data Storage &amp; Security</h2>
        <p>
          User accounts and simulation data are stored in
          <strong>Supabase</strong> (PostgreSQL). The application infrastructure
          runs on a <strong>Hetzner VPS</strong> located in the EU. All data is
          transmitted over encrypted connections (TLS). Access to production
          systems is restricted to authorized personnel only.
        </p>
      </section>

      <section>
        <h2>4. Cookies</h2>
        <p>
          Glas Intelligence uses <strong>essential cookies only</strong> — those
          required for authentication and session management. We do not use
          tracking cookies, advertising cookies, or third-party analytics cookies.
        </p>
      </section>

      <section>
        <h2>5. Third-Party Services</h2>
        <p>We share data with the following third-party processors, strictly as needed to operate the service:</p>
        <ul>
          <li>
            <strong>Stripe</strong> — Payment processing. Subject to
            <a href="https://stripe.com/privacy" target="_blank" rel="noopener">Stripe's Privacy Policy</a>.
          </li>
          <li>
            <strong>Supabase</strong> — Database and authentication. Subject to
            <a href="https://supabase.com/privacy" target="_blank" rel="noopener">Supabase's Privacy Policy</a>.
          </li>
          <li>
            <strong>Resend</strong> — Transactional email delivery. Subject to
            <a href="https://resend.com/legal/privacy-policy" target="_blank" rel="noopener">Resend's Privacy Policy</a>.
          </li>
        </ul>
      </section>

      <section>
        <h2>6. Your Rights (GDPR)</h2>
        <p>If you are located in the European Economic Area, you have the right to:</p>
        <ul>
          <li><strong>Access</strong> the personal data we hold about you.</li>
          <li><strong>Rectify</strong> inaccurate or incomplete data.</li>
          <li><strong>Erase</strong> your personal data ("right to be forgotten").</li>
          <li><strong>Restrict</strong> processing of your data in certain circumstances.</li>
          <li><strong>Port</strong> your data in a structured, machine-readable format.</li>
          <li><strong>Object</strong> to processing based on legitimate interests.</li>
        </ul>
        <p>To exercise any of these rights, contact us at the address below.</p>
      </section>

      <section>
        <h2>7. Data Deletion</h2>
        <p>
          You may request deletion of your account and all associated data at any
          time by contacting support. Upon receiving a verified request, we will
          delete your personal data within 30 days, except where retention is
          required by law or for legitimate business purposes (e.g., billing
          records).
        </p>
      </section>

      <section>
        <h2>8. Changes to This Policy</h2>
        <p>
          We may update this Privacy Policy periodically. Material changes will be
          communicated via email or in-app notice. The "Last updated" date at the
          bottom reflects the most recent revision.
        </p>
      </section>

      <section>
        <h2>9. Contact</h2>
        <p>
          For privacy-related inquiries, contact us at
          <a href="mailto:privacy@glasinsight.com">privacy@glasinsight.com</a>.
        </p>
      </section>

      <footer class="privacy-footer">Last updated: March 2026</footer>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.privacy-page {
  min-height: 100vh;
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  display: flex;
  justify-content: center;
  padding: 4rem 1.5rem;
}

.privacy-container {
  max-width: 720px;
  width: 100%;
}

h1 {
  font-size: 2rem;
  font-weight: 700;
  color: #ffffff;
  margin-bottom: 2.5rem;
  letter-spacing: -0.02em;
}

h2 {
  font-size: 1.15rem;
  font-weight: 600;
  color: #ffffff;
  margin-top: 2rem;
  margin-bottom: 0.75rem;
  letter-spacing: -0.02em;
}

p {
  font-size: 0.95rem;
  line-height: 1.7;
  color: #b0b0b0;
  margin-bottom: 0.75rem;
}

ul {
  padding-left: 1.25rem;
  margin-bottom: 0.75rem;
}

li {
  font-size: 0.95rem;
  line-height: 1.7;
  color: #b0b0b0;
  margin-bottom: 0.35rem;
}

li strong {
  color: #d0d0d0;
}

a {
  color: #4a9eff;
  text-decoration: none;
}

a:hover {
  text-decoration: underline;
}

section {
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding-bottom: 1.5rem;
}

section:last-of-type {
  border-bottom: none;
}

.privacy-footer {
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 0.85rem;
  color: #666;
}
</style>
