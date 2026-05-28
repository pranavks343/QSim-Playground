import dynamic from "next/dynamic";

import { Hero } from "@/components/landing/hero";
import { HowItWorks } from "@/components/landing/how-it-works";
import { Nav } from "@/components/shared/nav";

const AgentShowcase = dynamic(
  () => import("@/components/landing/agent-showcase").then((mod) => mod.AgentShowcase),
  { loading: () => <SectionSkeleton label="Loading agent showcase" /> }
);
const Honesty = dynamic(() => import("@/components/landing/honesty").then((mod) => mod.Honesty), {
  loading: () => <SectionSkeleton label="Loading benchmark honesty section" />
});
const TechStrip = dynamic(
  () => import("@/components/landing/tech-strip").then((mod) => mod.TechStrip),
  { loading: () => <SectionSkeleton label="Loading technology strip" /> }
);
const Footer = dynamic(() => import("@/components/shared/footer").then((mod) => mod.Footer), {
  loading: () => <SectionSkeleton label="Loading footer" />
});

export default function LandingPage() {
  return (
    <>
      <Nav />
      <main>
        <Hero />
        <HowItWorks />
        <AgentShowcase />
        <Honesty />
        <TechStrip />
      </main>
      <Footer />
    </>
  );
}

function SectionSkeleton({ label }: { label: string }) {
  return (
    <section className="border-t bg-background" aria-label={label}>
      <div className="mx-auto max-w-6xl px-4 py-12">
        <div className="h-28 rounded-lg bg-muted" />
      </div>
    </section>
  );
}
