import { Hero } from "@/components/landing/hero";
import { HonestySection } from "@/components/landing/honesty-section";
import { SiteNav } from "@/components/shared/site-nav";

export default function LandingPage() {
  return (
    <>
      <SiteNav />
      <main>
        <Hero />
        <HonestySection />
      </main>
    </>
  );
}
