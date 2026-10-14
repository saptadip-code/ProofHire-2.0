import { Globe, IndianRupee, Mail, MessageCircle, Timer, TrendingUp } from 'lucide-react';
import Reveal from './Reveal.jsx';

const SIGNALS = [
  { icon: IndianRupee, title: 'Upfront fees', text: 'Any request to pay a registration, training or security fee before an offer.' },
  { icon: TrendingUp, title: 'Unrealistic pay', text: 'Pay claims far above what an entry-level role normally offers.' },
  { icon: Mail, title: 'Free-email contact', text: 'Hiring handled from a free email address instead of a company domain.' },
  { icon: MessageCircle, title: 'Messaging-app hiring', text: 'Applications or interviews that happen only on WhatsApp or Telegram.' },
  { icon: Timer, title: 'Urgency pressure', text: 'Limited seats, apply today, and other wording that rushes your decision.' },
  { icon: Globe, title: 'Missing website', text: 'No company website to compare against the details in the listing.' },
];

export default function SignalGrid() {
  return (
    <div className="signal-grid">
      {SIGNALS.map((signal, index) => (
        <Reveal key={signal.title} delay={index * 70} className="signal-wrap">
          <div className="card card--lift signal">
            <span className="signal__icon">
              <signal.icon size={22} aria-hidden="true" />
            </span>
            <h3 className="signal__title">{signal.title}</h3>
            <p>{signal.text}</p>
          </div>
        </Reveal>
      ))}
    </div>
  );
}
