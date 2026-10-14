import HelpTip from './HelpTip.jsx';

// Label + control + hint + error wrapper. The caller wires aria-describedby using the ids below:
//   hint  -> `${id}-hint`      error -> `${id}-error`
// `help` adds a click-to-reveal help tip next to the label.
export default function FormField({ id, label, required = false, hint = null, error = null, counter = null, help = null, children }) {
  return (
    <div className={`field${error ? ' field--invalid' : ''}`}>
      <div className="field__labelrow">
        <label className="field__label" htmlFor={id}>
          {label}
          {required ? (
            <span className="field__req" aria-hidden="true">
              {' '}
              *
            </span>
          ) : (
            <span className="field__opt"> (optional)</span>
          )}
        </label>
        {help && <HelpTip label={label}>{help}</HelpTip>}
      </div>
      {children}
      <div className="field__meta">
        <div>
          {hint && (
            <p className="field__hint" id={`${id}-hint`}>
              {hint}
            </p>
          )}
          {error && (
            <p className="field__error" id={`${id}-error`} role="alert">
              <span className="field__error-label">Error: </span>
              {error}
            </p>
          )}
        </div>
        {counter && <span className="field__counter">{counter}</span>}
      </div>
    </div>
  );
}
