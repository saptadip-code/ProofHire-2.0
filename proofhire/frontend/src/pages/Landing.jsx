import { Link } from 'react-router-dom';
import { ArrowRight, ClipboardPaste, Gauge, ListChecks, ShieldCheck } from 'lucide-react';
import FaqAccordion from '../components/FaqAccordion.jsx';
import HeroPanel from '../components/HeroPanel.jsx';
import Reveal from '../components/Reveal.jsx';
import SignalGrid from '../components/SignalGrid.jsx';
import StatsStrip from '../components/StatsStrip.jsx';
import Timeline from '../components/Timeline.jsx';

const STEPS = [
  {
    icon: ClipboardPaste,
    title: 'Paste the listing',
    text: 'Enter the internship or job listing exactly as you found it, including pay, contact details and any fee.',
  },
  {
    icon: Gauge,
    title: 'Read the evidence',
    text: 'Get a risk estimate with the evidence behind it, split into what was observed in the listing and what the model derived.',
  },
  {
    icon: ListChecks,
    title: 'Verify the employer',
    text: 'Follow a checklist of concrete steps to check the employer yourself before you share data or pay anything.',
  },
];

export default function Landing() {
  return (
    <>
      <section className="hero-dark" aria-labelledby="hero-title">
        <div className="container hero-dark__inner">
          <div className="hero-dark__copy">
            <p className="eyebrow eyebrow--light">For students and early-career applicants</p>
            <h1 id="hero-title" className="hero-dark__title">
              Know what to check <span className="hero-dark__accent">before you apply.</span>
            </h1>
            <p className="hero-dark__lead">
              ProofHire gives an explainable risk estimate for internship and job listings, shows the evidence behind
              it, and guides you through verifying the employer.
            </p>
            <div className="hero-dark__actions">
              <Link to="/assess" className="btn btn-primary btn-lg">
                Assess a listing
                <ArrowRight size={18} aria-hidden="true" />
              </Link>
              <Link to="/about" className="btn btn-ghost btn-lg">
                How it works
              </Link>
            </div>
            <p className="hero-dark__note">
              <ShieldCheck size={16} aria-hidden="true" />A risk estimate, not a verification of the employer.
            </p>
          </div>
          <HeroPanel />
        </div>
      </section>

      <div className="container page landing">
        <StatsStrip />

        <section aria-labelledby="signals-title" className="section">
          <Reveal>
            <p className="eyebrow">What we look for</p>
            <h2 id="signals-title" className="section__title section__title--lg">
              Patterns that show up in risky listings
            </h2>
            <p className="muted section__lead">
              Each signal is shown with the exact text that triggered it, so you can judge it yourself.
            </p>
          </Reveal>
          <SignalGrid />
        </section>

        <section aria-labelledby="how-title" className="section">
          <Reveal>
            <p className="eyebrow">How it works</p>
            <h2 id="how-title" className="section__title section__title--lg">
              From a pasted listing to a verification plan
            </h2>
          </Reveal>
          <Timeline steps={STEPS} />
        </section>

        <Reveal as="section" className="honesty" aria-label="What ProofHire is and is not">
          <ShieldCheck size={22} aria-hidden="true" />
          <p>
            <strong>A risk estimate, not a verification.</strong> ProofHire cannot confirm that an employer is genuine.
            A low estimate does not mean a listing is safe, so always complete the checklist.
          </p>
        </Reveal>

        <section aria-labelledby="faq-title" className="section">
          <Reveal>
            <p className="eyebrow">Questions</p>
            <h2 id="faq-title" className="section__title section__title--lg">
              Good to know before you start
            </h2>
          </Reveal>
          <Reveal delay={80}>
            <FaqAccordion />
          </Reveal>
        </section>
      </div>
    </>
  );
}
