import { ChevronDown } from 'lucide-react';

const FAQS = [
  {
    q: 'Does a low risk score mean a listing is safe?',
    a: 'No. ProofHire gives a risk estimate, not a verification of the employer. A low estimate means fewer risk patterns were found, so you should still work through the verification checklist.',
  },
  {
    q: 'Where does the score come from?',
    a: 'A classical machine-learning model scores the listing from its text and structured details. The evidence panel separates what was observed directly in your listing from patterns the model derived.',
  },
  {
    q: 'Is the training data real?',
    a: 'No. The model is trained and evaluated on a synthetic dataset, so the dashboard metrics are labelled as a synthetic benchmark and do not prove the same performance on real listings.',
  },
  {
    q: 'Do I need an account?',
    a: 'No. You can assess a listing without signing in. An account lets you keep a saved list of your assessments and compare them later.',
  },
  {
    q: 'What should I never type into a listing form?',
    a: 'Your own ID numbers, passwords or bank details. ProofHire only needs the listing as you saw it.',
  },
];

// Native <details> keeps keyboard and screen-reader behaviour for free; CSS animates the chevron and panel.
export default function FaqAccordion() {
  return (
    <div className="faq">
      {FAQS.map((item) => (
        <details key={item.q} className="faq__item">
          <summary className="faq__q">
            <span>{item.q}</span>
            <ChevronDown size={20} aria-hidden="true" className="faq__chevron" />
          </summary>
          <p className="faq__a">{item.a}</p>
        </details>
      ))}
    </div>
  );
}
