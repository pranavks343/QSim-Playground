const tech = ["Qiskit", "IBM Quantum", "Gemini", "FastAPI", "Next.js"];

export function TechStrip() {
  return (
    <section className="bg-background">
      <div className="mx-auto max-w-6xl px-4 py-12">
        <p className="text-center text-sm font-medium text-muted-foreground">Built on</p>
        <div className="mt-6 flex flex-wrap justify-center gap-3">
          {tech.map((item) => (
            <span key={item} className="rounded-md border bg-card px-4 py-2 text-sm font-medium">
              {item}
            </span>
          ))}
        </div>
        <p className="mt-6 text-center text-sm text-muted-foreground">
          Runs real QAOA circuits on Qiskit Aer. IBM Quantum hardware support coming soon.
        </p>
      </div>
    </section>
  );
}
