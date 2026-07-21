const foundationItems = [
  "FastAPI composition root and safe health endpoints",
  "Next.js strict TypeScript application shell",
  "PostgreSQL, Redis, RabbitMQ, and MinIO local core",
  "Pinned upstream component manifest",
  "Permission-first and human-approval architecture boundaries",
] as const;

export default function HomePage() {
  return (
    <main>
      <section className="hero" aria-labelledby="page-title">
        <p className="eyebrow">Phase 0 · Foundation</p>
        <h1 id="page-title">Tactiqo AI Operations Platform</h1>
        <p className="summary">
          The local-first engineering foundation is in place. Production agents,
          connectors, and knowledge workflows remain behind their required review gates.
        </p>
        <ul>
          {foundationItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
        <div className="status" role="status">
          Architecture scaffold active · Business data not configured
        </div>
      </section>
    </main>
  );
}
