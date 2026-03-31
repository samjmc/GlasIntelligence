<template>
  <div class="terms-page">
    <div class="terms-container">
      <h1>Terms of Service</h1>

      <section>
        <h2>1. Service Description</h2>
        <p>
          Glas Intelligence is an AI-powered scenario simulation platform designed
          for structured analysis of complex systems. The platform enables users to
          model multi-agent interactions, generate scenario reports, and explore
          potential outcomes across policy, economic, and strategic domains.
        </p>
        <p class="disclaimer">
          Glas Intelligence provides structured scenario analysis. It does not issue
          forecasts or policy recommendations.
        </p>
        <p>
          Outputs are illustrative simulations, not financial advice, legal counsel,
          or policy directives. Users should not rely on simulation results as the
          sole basis for decision-making.
        </p>
      </section>

      <section>
        <h2>2. User Responsibilities</h2>
        <p>By using Glas Intelligence, you agree to:</p>
        <ul>
          <li>Provide accurate information when creating an account.</li>
          <li>Maintain the confidentiality of your login credentials.</li>
          <li>Use the platform only for lawful purposes.</li>
          <li>Not attempt to reverse-engineer, exploit, or disrupt the service.</li>
          <li>Not use automated tools to scrape or extract data from the platform.</li>
        </ul>
      </section>

      <section>
        <h2>3. Intellectual Property</h2>
        <p>
          All platform code, models, user interface designs, and branding are the
          intellectual property of Glas Intelligence. Simulation outputs generated
          by a user belong to that user, but Glas Intelligence retains the right to
          use anonymized, aggregated data to improve the service.
        </p>
      </section>

      <section>
        <h2>4. Payment Terms</h2>
        <p>
          Glas Intelligence offers subscription plans, pay-as-you-go simulation
          purchases, and simulation packs. All payments are processed securely
          through Stripe. Subscription fees are billed on a recurring monthly basis.
          Purchased simulations do not expire. Refunds are handled on a case-by-case
          basis; contact support for assistance.
        </p>
      </section>

      <section>
        <h2>5. Limitation of Liability</h2>
        <p>
          Glas Intelligence is provided "as is" without warranties of any kind,
          express or implied. We do not guarantee the accuracy, completeness, or
          reliability of any simulation output. In no event shall Glas Intelligence
          be liable for any indirect, incidental, consequential, or punitive damages
          arising from the use of, or inability to use, the service.
        </p>
      </section>

      <section>
        <h2>6. Data Handling</h2>
        <p>
          We collect and process personal data in accordance with our
          <router-link to="/privacy">Privacy Policy</router-link>. Simulation data,
          uploaded documents, and generated reports are stored securely and are
          accessible only to the account holder unless explicitly shared.
        </p>
      </section>

      <section>
        <h2>7. Termination</h2>
        <p>
          You may close your account at any time by contacting support. We reserve
          the right to suspend or terminate accounts that violate these terms,
          engage in abusive behaviour, or pose a security risk to the platform. Upon
          termination, your data will be deleted in accordance with our data
          retention policy.
        </p>
      </section>

      <section>
        <h2>8. Changes to These Terms</h2>
        <p>
          We may update these terms from time to time. Material changes will be
          communicated via email or an in-app notice. Continued use of the service
          after changes take effect constitutes acceptance of the revised terms.
        </p>
      </section>

      <section>
        <h2>9. Contact</h2>
        <p>
          For questions about these terms, contact us at
          <a href="mailto:support@glasinsight.com">support@glasinsight.com</a>.
        </p>
      </section>

      <footer class="terms-footer">Last updated: March 2026</footer>
    </div>
  </div>
</template>

<script setup>
</script>

<style scoped>
.terms-page {
  min-height: 100vh;
  background: #0a0a0a;
  color: #e0e0e0;
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  display: flex;
  justify-content: center;
  padding: 4rem 1.5rem;
}

.terms-container {
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

.disclaimer {
  background: rgba(255, 255, 255, 0.04);
  border-left: 3px solid #4a9eff;
  padding: 0.75rem 1rem;
  border-radius: 4px;
  font-style: italic;
  color: #c0c0c0;
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

.terms-footer {
  margin-top: 3rem;
  padding-top: 1.5rem;
  border-top: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 0.85rem;
  color: #666;
}
</style>
