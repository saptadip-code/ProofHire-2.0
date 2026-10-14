import EmptyState from './EmptyState.jsx';
import { formatCount } from '../lib/format.js';

// 2x2 grid with counts. "Risky" is the positive class.
export default function ConfusionMatrix({ matrix }) {
  if (!matrix) {
    return <EmptyState title="Confusion matrix not available" message="The metrics file did not include one." />;
  }
  return (
    <div className="table-wrap">
      <table className="confusion">
        <caption className="sr-only">Confusion matrix on the synthetic benchmark</caption>
        <thead>
          <tr>
            <td />
            <th scope="col">Predicted: lower risk</th>
            <th scope="col">Predicted: risky</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <th scope="row">Actual: legitimate</th>
            <td className="confusion__cell">
              <strong>{formatCount(matrix.tn)}</strong>
              <span>True negatives</span>
            </td>
            <td className="confusion__cell">
              <strong>{formatCount(matrix.fp)}</strong>
              <span>False positives</span>
            </td>
          </tr>
          <tr>
            <th scope="row">Actual: risky</th>
            <td className="confusion__cell">
              <strong>{formatCount(matrix.fn)}</strong>
              <span>False negatives</span>
            </td>
            <td className="confusion__cell">
              <strong>{formatCount(matrix.tp)}</strong>
              <span>True positives</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
