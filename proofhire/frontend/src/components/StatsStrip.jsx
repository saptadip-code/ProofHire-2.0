import AnimatedNumber from './AnimatedNumber.jsx';
import Reveal from './Reveal.jsx';

// Facts about how the product works (not usage claims), so every number here is checkable in the app.
const STATS = [
  { value: 17, label: 'listing details analysed', hint: 'Title, pay, contact, fee, channel and more' },
  { value: 2, label: 'kinds of evidence', hint: 'Observed in the listing, and model-derived' },
  { value: 3, label: 'risk levels', hint: 'Always shown with an icon and a text label' },
  { value: 0, label: 'employers verified', hint: 'An estimate is never a verification' },
];

export default function StatsStrip() {
  return (
    <Reveal as="section" className="stats" aria-label="ProofHire at a glance">
      <ul className="stats__grid">
        {STATS.map((stat) => (
          <li key={stat.label} className="stats__item">
            <p className="stats__value">
              <AnimatedNumber value={stat.value} />
            </p>
            <p className="stats__label">{stat.label}</p>
            <p className="stats__hint">{stat.hint}</p>
          </li>
        ))}
      </ul>
    </Reveal>
  );
}
