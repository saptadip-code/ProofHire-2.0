import Reveal from './Reveal.jsx';

// Numbered steps joined by a line that draws itself as the list scrolls into view.
export default function Timeline({ steps }) {
  return (
    <ol className="timeline">
      {steps.map((step, index) => (
        <Reveal as="li" key={step.title} delay={index * 120} className="timeline__item">
          <span className="timeline__node" aria-hidden="true">
            <step.icon size={20} />
          </span>
          <div className="card card--lift timeline__card">
            <p className="eyebrow">Step {index + 1}</p>
            <h3 className="timeline__title">{step.title}</h3>
            <p>{step.text}</p>
          </div>
        </Reveal>
      ))}
    </ol>
  );
}
